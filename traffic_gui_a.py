"""
列車運行情報(データ引用：Yahoo路線情報)

[ 参考サイト ]  
Quita:  
https://qiita.com/y_sayama/items/f73d1f50ed4041d14c16  
Yahoo路線情報:  
https://transit.yahoo.co.jp/

"""

import tkinter.ttk as ttk
import tkinter.font
import os
import requests
import time
import textwrap
import sys
import threading
import gc
import webbrowser
from tkinter import *
from tkinter import messagebox
from bs4 import BeautifulSoup
from PIL import Image, ImageTk, ImageFilter
from datetime import datetime, timedelta

# メインウィンドウ作成
root = Tk()

# メインウィンドウサイズ(最低ライン)
root.geometry("1300x700")
# ウィンドウサイズを固定
root.resizable(False, False)
# メインウィンドウタイトル
root.title("列車運行情報")

# --- ↓↓↓ 任意 --- 
# アイコン画像とパスを設定：かなり小さくなるが任意のiconに変更可能
# icon_path = os.path.join(os.path.dirname(__file__), "任意の .ico ファイル")
# アイコンをウィンドウに設定
# root.iconbitmap(icon_path)
# --- ↑↑↑ ここまで ---

# --- ↓↓↓ 路線の設定は自由に… ↓↓↓ ---
# Yahoo路線情報URL
url_dict = {
    "東海道新幹線": "https://transit.yahoo.co.jp/diainfo/7/0", 
    "大阪環状線": "https://transit.yahoo.co.jp/diainfo/263/0",
    "南海本線": "https://transit.yahoo.co.jp/diainfo/339/0", 
    "大和路(関西本)線": "https://transit.yahoo.co.jp/diainfo/277/0",
    "サンライズ出雲・瀬戸": "https://transit.yahoo.co.jp/diainfo/1052/0"
}

# 鉄道会社公式サイトURL
railway_company_urls = {
    "東海道新幹線": "https://jr-central.co.jp/",
    "大阪環状線": "https://www.jr-odekake.net/",
    "南海本線": "https://www.nankai.co.jp/",
    "大和路(関西本)線": "https://www.jr-odekake.net/",
    "サンライズ出雲・瀬戸": "https://www.jreast.co.jp/"
}

# 運行情報対象路線
train_list = [
    "東海道新幹線",
    "大阪環状線", 
    "南海本線", 
    "大和路(関西本)線",
    "サンライズ出雲・瀬戸"
]

# 路線の区間情報(運行情報対象区間)
train_section = {
    "東海道新幹線": "新大阪 ～ 東京", 
    "大阪環状線": "内回り・外回り",
    "南海本線": "なんば ～ 和歌山市",
    "大和路(関西本)線": "JR難波 ～ 加茂",
    "サンライズ出雲・瀬戸": "東京 ～ 出雲市・高松(琴平)"
}
# --- ↑↑↑ 路線の設定は自由に…  ↑↑↑ ---


# MainFrame クラス
class MainFrame(ttk.Frame):

    # コンストラクタ
    def __init__(self, master=None, **kwargs):
        # 親クラスのコンストラクタを呼び出す
        super().__init__(master, **kwargs)
        self.is_fullscreen_active = False # フルスクリーン状態
        self.initial_geometry = "1300x750" # 初期ウィンドウサイズ
        self.running = True # メインループの実行状態フラグ
        self.scrolling_tasks = {} 
        self.WRAP_WIDTH = 10 # 折り返し幅
        self.MAX_LINES = 2 # 最大表示行数
        self.SCROLL_SPEED_PIXELS = 2 # スクロール速度(ピクセル単位)
        self.SCROLL_INTERVAL_MS = 50 # スクロール間隔(ミリ秒単位)
        self.update_scheduled_but_pending = False # 更新が保留されているか示すフラグ
        
        # このスプリクトの絶対パス
        self.scr_path = os.path.dirname(os.path.abspath(__file__))
        # 路線情報アイコンパス(ディクショナリ)
        self.icon_dict = {
            "normal": Image.open(self.scr_path + "/img/train.png"),
            "trouble": Image.open(self.scr_path + "/img/warning.png"),
            "shinkansen": Image.open(self.scr_path + "/img/jnr_0.png")
        }
        
        # ニュース関連設定
        self.news_scroll_task_key = "news_headlines_scroll"
        self.news_font_size = 24
        self.news_font = "MS Gothic", self.news_font_size
        self.news_font_object = tkinter.font.Font(font=self.news_font)
        # ニュース更新間隔(ミリ秒) (15分に1回更新)
        self.NEWS_UPDATE_INTERVAL_MS = 15 * 60 * 1000
        # ニュースURL: Yahoo国内ニュース
        self.NEWS_URL = "https://news.yahoo.co.jp/categories/domestic"

        # 路線情報用アイコンをリサイズ
        for key, value in self.icon_dict.items():
            self.icon_dict[key] = self.icon_dict[key].resize((64, 64), Image.LANCZOS)
            self.icon_dict[key] = ImageTk.PhotoImage(self.icon_dict[key])
        
        # --- ↓↓↓ Windows の場合のみディスプレイスリープ防止設定 ---
        self._initialize_styles_and_urls() # スタイルとURLを初期化
        if sys.platform == "win32":
            try:
                self.ctypes = __import__("ctypes") # Windows の場合 ctypes をインポート
                self.ES_CONTINUOUS = 0x80000000 # Windows のフルスクリーン定数
                self.ES_DISPLAY_REQUIRED = 0x00000002 # ディスプレイを常にオンにする定数
                self.ctypes.windll.kernel32.SetThreadExecutionState(
                    self.ES_CONTINUOUS | self.ES_DISPLAY_REQUIRED
                ) # ディスプレイを常にオンにする
            except Exception as e:
                print(f"ディスプレイのスリープ防止設定に失敗しました：{e}") # debug
        # --- ↑↑↑ ここまで ---
        
        # create_widgets を呼び出す
        self.create_widgets()
        
    # 路線名を指定幅で折り返し、最大指定行数で返す
    def _format_routename_for_display(self, routename):
        if not routename:
            return ""
        # routename が None の場合や空文字列の場合の処理
        wrapped_lines = textwrap.wrap(str(routename), width=self.WRAP_WIDTH)
        return "\n".join(wrapped_lines[:self.MAX_LINES]) # 最大行数まで折り返し
    
    # 手動で運行情報を更新
    def trigger_manual_update(self):
        print("手動で運行情報を更新します") # debug
        if self.running: # 実行中のみ更新
            try:
                self.update_train_info_internal() # 運行情報を更新
            except Exception as e:
                print(f"エラーが発生しました：{e}") # debug

    # ウィジェットを作成
    def create_widgets(self):
        # フレームを作成
        self.header_frame = Frame(self, bg="AntiqueWhite2", bd=0, relief="flat")

        # フレームを配置
        self.header_frame.grid(row=0, column=0, columnspan=3, sticky="news")
        
        # header_frame (内部 grid 設定)
        self.header_frame.columnconfigure(0, weight=0) # タイトル列(コンテンツ幅)
        self.header_frame.columnconfigure(1, weight=0) # 日時列(コンテンツ幅)
        self.header_frame.columnconfigure(2, weight=1) # スペーサー列(伸縮)
        self.header_frame.columnconfigure(3, weight=0) # 更新ボタン列(コンテンツ幅)
        
        #タイトルの表示
        self.title_lbl = Label(self.header_frame,
                             text=" 鉄道路線運行情報 ", 
                             bg="aqua", # 背景色 
                             font=("", 50) # フォント
                             )

        # タイトルの配置
        self.title_lbl.grid(row=0, # 行
                            column=0, # 列
                            sticky="w", # 位置
                            # 時刻ラベルとの位置調整用
                            padx=(40, 50), # 左パディング、右パディング
                            pady=15
                            )
        
        # 現在時刻とカスタムテキスト用のコンテナフレーム
        datetime_area_frame = Frame(self.header_frame, bg="AntiqueWhite2") # 背景色( header_frame と同色 )
        # datetime_frame と同じ grid 配置で設定
        datetime_area_frame.grid(row=0, column=1, sticky="w", padx=(0, 20), pady=15)        
        # 現在時刻を表示するラベル
        self.datetime_label = Label(datetime_area_frame, text="0",bg="AntiqueWhite2", font=("", 30))
        self.datetime_label.pack(side=TOP, anchor="w")
        self.update_datetime()
        # 時刻の下に表示するテキストラベル
        self.custom_masseage_label = Label(
                                            datetime_area_frame,
                                            text="情報提供：Yahoo路線情報", # 任意のテキスト
                                            bg="AntiqueWhite2", # 背景色
                                            font=("", 20), # フォント
                                            fg="midnightblue" # 文字色
                                        )
        self.custom_masseage_label.pack(side=TOP, anchor="e", pady=(5,0)) # datetime_label の下に配置
        
        # ボタン用コンテナフレームを header_frame に作成
        buttons_container = Frame(self.header_frame, bg=self.header_frame.cget("bg"))
        # stycky="ne" でコンテナをセル(右上)に配置
        # padx で 左右, pady で 上下 を調整(余白)
        buttons_container.grid(row=0, column=3, sticky="ne", padx=(30, 30), pady=5)
        
        # --- ↓↓↓ タッチパネル対応ボタンを作成(PCでも使用可) ---
        # 構造はほぼ同一
        # 手動更新ボタン
        self.update_button = Button(
                                    buttons_container, 
                                    text="手動更新", 
                                    bg=self.header_frame.cget("bg"), # ボタンの背景色
                                    fg="navy", # 文字色
                                    bd=2, # 境界線
                                    font=("", 10), # フォント
                                    relief="raised", # 3D効果
                                    activebackground="lightgray", # ホバー時の背景色
                                    highlightthickness=0, # ハイライト時の境界線
                                    command=self.trigger_manual_update, # 既存のメソッドを呼び出す
                                    padx=3,
                                    pady=3
                                    )

        # pack でボタンを配置, fill=X は横幅を コンテナの幅に合わせ, pady で上下のボタンとの間を調整
        self.update_button.pack(side=TOP, fill=X, pady=(0,2)) # 下に配置, 上にスペース
        
        # フルスクリーンボタン
        self.fullscreen_button = Button(
                                        buttons_container,
                                        text="フルスクリーン", 
                                        bg=self.header_frame.cget("bg"),
                                        bd=2,
                                        font=("", 10),
                                        relief="raised", 
                                        activebackground="lightgray",
                                        highlightthickness=0,
                                        command=self.toggle_fullscreen,
                                        padx=3,
                                        pady=3
                                        )
        
        self.fullscreen_button.pack(side=TOP, fill=X, pady=2)
        
        # フルスクリーン解除ボタン
        self.restore_fullscreen_button = Button(
                                                buttons_container,
                                                text="フルスクリーン解除", 
                                                bg=self.header_frame.cget("bg"),
                                                bd=2, 
                                                font=("", 10),
                                                relief="raised", 
                                                activebackground="lightgray",
                                                highlightthickness=0,
                                                command=self.restore_to_original_size,
                                                padx=3,
                                                pady=3
                                                )
        
        self.restore_fullscreen_button.pack(side=TOP, fill=X, pady=2)
        
        # 終了ボタン
        self.quit_button = Button(
                                buttons_container,
                                text="終了", 
                                bg=self.header_frame.cget("bg"),
                                fg="red",
                                bd=2, 
                                font=("", 10),
                                relief="raised", 
                                activebackground="lightgray",
                                highlightthickness=0,
                                command=self.on_close,
                                padx=3,
                                pady=3
                                )
        
        self.quit_button.pack(side=TOP, fill=X, pady=(2,0))
        # --- ↑↑↑ ここまで ---
        
        # ヘッダーの下に罫線 sticky="ew"は左右(eastwest)寄せ
        header_separator = ttk.Separator(self, orient=HORIZONTAL)
        header_separator.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(1, 1))
        
        
    # スタイル情報とURL情報を初期化, インスタンス変数として保持        
    def _initialize_styles_and_urls(self):
        self.railway_company_urls = railway_company_urls # グローバル変数をインスタンス変数にコピー
        # --- ↓↓↓ 路線名表示スタイル(変更できる部分はお好みで…) ---
        # ※ このリストも編集しないと、bg, fg ともにデフォルトで表示される
        self.train_styles = {
            "東海道新幹線":{"bg":"blue2", "fg":"white"},
            "大阪環状線":{"bg":"darkorange1", "fg":"white"},
            "南海本線":{"bg":"yellow green", "fg":"white"},
            "大和路(関西本)線":{"bg":"gray", "fg":"white"},
            "サンライズ出雲・瀬戸":{"bg":"magenta2", "fg":"white"}
        }
        # --- ↑↑↑ ここまで ---
        
        # 路線名を表示するためのラベルを作成
        self.wwl = [] # 路線名のリスト
        self.wws = [] # 対象区間のリスト
        for train_name in train_list: # global関数 train_list を使用
            company_url_to_open = self.railway_company_urls.get(train_name) # インスタンス変数を削除
            # インスタンス変数 self.train_styles を使用
            style = self.train_styles.get(train_name, {"bg":"lightgray","fg":"black"}) # デフォルト
            formatted_name = self._format_routename_for_display(train_name)
            # 路線名用ラベル
            label = Label(
                        self, # self はインスタンス変数 
                        text=formatted_name, 
                        bg=style["bg"], # self.train_styles を参照
                        font=("", 26, "bold"), 
                        fg=style["fg"]
                        )
            # 区間用ラベル
            section_label = Label(
                                self, 
                                text="", 
                                bg=style["bg"], 
                                font=("", 22, "bold"), 
                                fg=style["fg"]
                                )
            # URLが設定されている場合のみクリックイベントをバインド
            if company_url_to_open: 
                # イベントバインディング
                # URL が設定されている場合のみクリックイベントをバインド
                label.bind(
                            "<ButtonPress-1>", # 左クリック 
                            lambda e, # イベントオブジェクト
                            lbl=label, # イベントバインドするラベル
                            name=train_name: self.on_routename_press(lbl, name) # イベントバインドする関数
                            ) 
                label.bind(
                            "<ButtonRelease-1>",
                            lambda e,
                            lbl=label,
                            url=company_url_to_open,
                            name=train_name: self.on_routename_release(lbl, url, name))
            self.wwl.append(label) # 路線名用ラベルをリストに追加
            self.wws.append(section_label) # 区間用ラベルをリストに追加
            
        self.wwi = [] # 運転状況用ラベル
        for _ in range(len(train_list)): # train_list の数に応じてラベルを作成
            label = Label(self, image=self.icon_dict["normal"], bg="white") # 運転状況用ラベル
            self.wwi.append(label) # ラベルをリストに追加(append)

        # 運転状況用 Canvas
        self.wwt_canvas = [] 
        self.status_font = ("MS Gothic", 40)
        self.status_font_object = tkinter.font.Font(font=self.status_font) # フォントオブジェクト
        
        for i in range(len(train_list)): # train_list の数に応じて Canvas を作成
            font_metrics = self.status_font_object.metrics()
            # Canvasの高さをフォントメトリクスから計算
            canvas_height = font_metrics["ascent"] + font_metrics["descent"] + 4 # fallback 高さを計算
            canvas = Canvas(self, bg="white", height=canvas_height, highlightthickness=0)
            # configure をバインド
            canvas.bind("<Configure>", # キャンバスのサイズが変更されたとき
                lambda event, # イベントオブジェクト
                c=canvas, # イベントバインドするCanvas
                idx=i: self._on_canvas_configure(event, c, idx) # _on_canvas_configure を呼び出す
            )
            self.wwt_canvas.append(canvas) # Canvas をリストに追加
               
        # 路線情報を縦に並べる(各路線の情報を1行に表示)
        base_row_for_trains = 2 # 路線情報表示の開始行
        for i in range(len(self.wwl)): # len(self.wwl)は路線数
            current_display_row = base_row_for_trains + (i * 3) 
            # ↑↑↑ 
            # example: current_display_row = 1 + (i * 2) #ヘッダーの下行から開始 各路線2行
            # 各路線ブロックは、路線情報2行 + 下の罫線1行と合わせて3行占めるという考え
            # ↑↑↑
            
            # 路線情報を表示 sticky="news"は上下左右(north, south, east, west)
            self.wwl[i].grid(row=current_display_row, column=0, sticky="news") # 路線名
            self.wws[i].grid(row=current_display_row + 1, column=0, sticky="news") # 路線名の下に対象区間
            self.wwi[i].grid(row=current_display_row, column=1, rowspan=2, sticky="news") # アイコン
            self.wwt_canvas[i].grid(row=current_display_row, column=2, rowspan=2, sticky="news") # 運行状況
            # アイコンの左に垂直罫線( orient=VERTICAL )を表示 sticky="nsw"は上下左(north,south west)
            left_vertical_separator = ttk.Separator(self, orient=VERTICAL) # 罫線
            left_vertical_separator.grid(row=current_display_row, column=1, sticky="nsw", rowspan=2)    
            # アイコンの右に垂直罫線を表示
            right_vertical_separator = ttk.Separator(self, orient=VERTICAL)
            right_vertical_separator.grid(row=current_display_row, column=2, sticky="nsw", rowspan=2)    
            # 各路線直下( orient=HORIZONTAL )に水平方向に罫線を表示
            train_separator = ttk.Separator(self, orient=HORIZONTAL)
            train_separator.grid(row=current_display_row + 2, column=0, columnspan=3, sticky="ew", pady=(1, 1))
                         
        self.rowconfigure(0, weight=0) # header_frame(固定または内容に依存)
        self.rowconfigure(1, weight=0) # ヘッダー下の罫線
        num_trains = len(self.wwl)
        for i in range(num_trains):
            # self.rowconfigure(i + 1, weight=1) # 各路線運行がスペースを広げる
            # 各路線ブロックが使用する2行に weight を設定
            base_row_index = base_row_for_trains + (i * 3)
            self.rowconfigure(base_row_index, weight=1) # 路線名行
            self.rowconfigure(base_row_index + 1, weight=1) # 区間名
            # 罫線行は常に固定( weight=0 )
            self.rowconfigure(base_row_index + 2, weight=0) # 罫線行
                
        # メインフレームの列判定(路線名・アイコン・状況)
        self.columnconfigure(0, weight=0) # 路線名列の幅を内容に合わせて伸縮
        self.columnconfigure(1, weight=0) # アイコン列は固定がいい場合がある
        self.columnconfigure(2, weight=1) # 運行状況
        
        # メインフレームにニュース表示を追加
        add_news_display_to_mainframe(self)
        
    def _on_canvas_configure(self, event, canvas_widget, index):
        # Canvasのサイズが変更されたときに呼び出される
        # スクロール中でないテキストの位置を更新
        task_info = self.scrolling_tasks.get(index) # index = 路線情報の場合は数値, ニュースの場合文字列キー
        if task_info and len(task_info) == 12: # 12要素のタスク情報
            canvas_widget, text_item_id, _displayed_text, _after_id, text_pixel_width, _current_x_pos, _initial_y_pos, scroll_active, _is_trouble, _font_obj, _speed, _interval = task_info
            
            if not scroll_active and text_item_id: # 静的表示の場合
                canvas_width = canvas_widget.winfo_width()
                canvas_height = canvas_widget.winfo_height()
                
                if canvas_width <= 1 or canvas_height <= 1:
                    # サイズがまだ決まっていない場合、デフォルト値を使用
                    return
                # text_item は anchor = "center" で作成されている
                # x座標は canvas の幅半分に設定することで中央揃えになる
                new_x = canvas_width / 2 # 水平中央揃え
                new_y = canvas_height / 2 # 垂直中央揃え
                
                canvas_widget.coords(text_item_id, new_x, new_y)

    # スクロール処理
    def _scroll_text_step(self, task_key):
        if task_key not in self.scrolling_tasks:
            return # スクロールが停止されたか、タスクが存在しない

        # タスク情報を取得
        task_data = self.scrolling_tasks[task_key]
        canvas_widget, text_item_id, _, new_after_id, text_width_pixels, current_x_pos, initial_y_pos, scroll_active, is_trouble_scroll, _, scroll_speed_px, _scroll_interval_ms_val = task_data
        
        if not scroll_active: # スクロールが不要または停止した場合
            return # 何もしない
        
        # テキストを左にスクロール
        new_x_pos = current_x_pos - scroll_speed_px
        
        # テキストが左端で完全に消えたら 右端に再配置
        # anchor = "w"の場合 : if_new_x_pos + text_width_pixels < 0:
        # anchor = "center" の場合 : text中央が new_x_pos, text右端は new_x_pos + text_width_pixels / 2
        if new_x_pos + (text_width_pixels / 2) < 0: # text右端が左端を通過した
            # text 中央を canvas の右端 + text 幅の半分の位置に再移動
            # テキストの左端がcanvasの右端に配置, 右からスムーズに再スクロールされる
            new_x_pos = canvas_widget.winfo_width() + (text_width_pixels / 2)

        # 1ループ毎に更新されるため、スクロール処理中に更新が必要な場合は保留
        if is_trouble_scroll and self.update_scheduled_but_pending:
            # アクティブなトラブルスクロールがないか確認
            if not self.is_any_active_trouble_scroll(exclude_current_index=task_key):
                print(f"スクロール完了：(タスクキー:{task_key}), 保留されていた更新をスケジュールします")
                self.after(0, self._execute_pending_update) # 保留されていた更新を実行
                self.update_scheduled_but_pending = False # 保留解除

        canvas_widget.coords(text_item_id, new_x_pos, initial_y_pos)
            
        # 新しいafter_id をスケジュール
        new_after_id = self.after(_scroll_interval_ms_val, self._scroll_text_step, task_key)
        # タスク情報を更新
        self.scrolling_tasks[task_key] = (
                                        canvas_widget,
                                        text_item_id, 
                                        task_data[2], # 表示テキスト 
                                        new_after_id, 
                                        text_width_pixels, 
                                        new_x_pos, 
                                        initial_y_pos,
                                        True, 
                                        is_trouble_scroll,
                                        task_data[9], # font_object
                                        scroll_speed_px,
                                        _scroll_interval_ms_val
                                        )

    # スクロール開始
    def start_scrolling(
                        self,
                        canvas_widget,
                        original_text,
                        task_key, 
                        text_fill_color="black",
                        font_object=None,
                        scroll_speed_pixels=None,
                        scroll_interval_ms=None,
                        is_trouble_scroll=False
                        ):

        # 既存のスクロールを停止
        self.stop_scrolling(task_key)

        # スクロールさせるための1行テキスト（元テキストの改行はスペースに置換されている想定）
        text_for_scrolling = original_text.strip()
        
        # フォントオブジェクトとスクロールパラメータの取得
        current_font_object = font_object if font_object else self.status_font_object
        current_scroll_speed = scroll_speed_pixels if scroll_speed_pixels is not None else self.SCROLL_SPEED_PIXELS
        # --- ↓↓↓ 三項演算子 ---
        # if scroll_speed_pixels is not None:
        #   current_scroll_speed = scroll_speed_pixels
        # else:
        #   current_scroll_speed = self.SCROLL_SPEED_PIXELS
        #
        # scroll_speed_pixels が None でないかを確認し、
        # None でなければ current_scroll_speed に scroll_speed_pixels を代入し、
        # そうでなければ self.SCROLL_SPEED_PIXELS を代入するという処理を、
        # 最初の if-else ブロックで表現
        # --- ↑↑↑ ---
        current_scroll_interval = scroll_interval_ms if scroll_interval_ms is not None else self.SCROLL_INTERVAL_MS
        # --- ↓↓↓ 三項演算子 ---
        # if scroll_interval_ms is not None:
        #   current_scroll_interval = scroll_interval_ms
        # else:
        #   current_scroll_interval = self.SCROLL_INTERVAL_MS
        #
        # scroll_interval_ms が None でないかを確認し、
        # 条件に応じて current_scroll_interval に値を代入する処理を、
        # 2つ目の if-else ブロックで表現
        # --- ↑↑↑ ---
        current_font_spec = current_font_object.actual() # フォント指定を取得(タプル or 辞書)
        # create_text は (family, size, weight) のタプルを期待
        font_family = current_font_spec.get("family", "MS Gothic")
        font_size = current_font_spec.get("size", 24)
        font_weight = current_font_spec.get("weight", "normal")
        font_for_canvas = (font_family, font_size, font_weight)
        

        # Canvasの 幅と高さ を取得
        # grid されているので ある程度は値が取れるはず
        canvas_widget.update_idletasks() # サイズ取得前にUIイベントを処理
        canvas_width = canvas_widget.winfo_width() # Canvas の幅
        if canvas_width <= 1: # まだ描画されていない場合 デフォルトや推定値を使う
            canvas_width = 300 # 仮
        canvas_height = canvas_widget.winfo_height() # Canvas の高さ
        if canvas_height <= 1:
            font_metrics = current_font_object.metrics() # フォントメトリクスを取得
            canvas_height = font_metrics["ascent"] + font_metrics["descent"] + 4 # fallback 高さを計算

        # テキストの pixel を計算
        text_width_pixels = current_font_object.measure(text_for_scrolling)
        # ↓↓↓ y 座標は Canvas 垂直方向中央を基準
        # example: 上に表示したい場合 canvas_height // 2 - 5
        # example: 下に表示したい場合 canvas_height // 2 + 5
        initial_y_pos = canvas_height // 2 # オフセットを削除、中央基準
        # ↑↑↑
        
        # 既存のアイテムがあれば削除
        # stop_scrolling メソッドで削除されるので、ここでは削除しない
        # 基本的には削除
        # canvas_widget.delete("scroll_text_" + str(index))
        
        # is_trouble_scroll = (text_fill_color == "red") # トラブルかどうかのフラグ
    
        # タグ名は task_key を含め統一する
        canvas_item_tag = str(task_key) + "_text"
        canvas_widget.delete(canvas_item_tag)
    
        if text_width_pixels > canvas_width:
            # スクロールを要する場合
            scroll_separator = "  ◆◆◆  " # 区切り文字
            display_text = scroll_separator + text_for_scrolling + scroll_separator 
            text_width_pixels = current_font_object.measure(display_text) # 区切り文字を含めた幅で再計算
            
            # anchor="center" の場合, text中央が initial_x_pos に来る
            # text全体を 右からスクロールさせるには
            initial_x_pos = canvas_widget.winfo_width() + (text_width_pixels / 2) # canvasの右端 + text幅の半分
            text_item_id = canvas_widget.create_text( # Canvasにテキストを追加
                initial_x_pos, # 初期X座標 (text中央)
                initial_y_pos, # 初期Y座標
                text=display_text, # 区切り文字を含めたテキスト
                font=font_for_canvas, # フォント
                anchor="center", # 中央寄せで座標指定
                fill=text_fill_color, # 文字色
                tags=canvas_item_tag # タグ
            )
            
            after_id = self.after(current_scroll_interval, self._scroll_text_step, task_key) # スクロールステップをスケジュール
            self.scrolling_tasks[task_key] = ( # タスク情報を保存
                canvas_widget, # Canvas Widget
                text_item_id, # テキストアイテムID
                display_text, # 表示テキスト
                after_id, # スクロールステップをスケジュールするafter_id
                text_width_pixels, # 表示テキストの幅
                initial_x_pos, # 初期X座標
                initial_y_pos, # 初期Y座標
                True, # スクロール中
                is_trouble_scroll, # トラブルかどうか
                current_font_object, # フォント
                current_scroll_speed, # スクロール速度
                current_scroll_interval, # スクロール間隔                
            )
        else:
            # label_widget.configure(text=text_for_scrolling)
            # スクロール不要 静的表示( anchor="w" と initial_x_pos の計算で水平中央揃え)
            initial_x_pos = canvas_width / 2 # 水平中央
            text_item_id = canvas_widget.create_text(
                initial_x_pos, 
                initial_y_pos, 
                text=text_for_scrolling,
                font=font_for_canvas,
                anchor="center", # 中央寄せで座標指定
                fill=text_fill_color,
                tags=canvas_item_tag
            )
            
            self.scrolling_tasks[task_key] = (
                canvas_widget, 
                text_item_id,
                text_for_scrolling, # 表示テキスト
                None, # after_id (スクロールしない)
                text_width_pixels,
                initial_x_pos, # 水平中央揃えのための初期X座標
                initial_y_pos, # 垂直方向中央揃えのための初期Y座標
                False, # スクロール中フラグ
                is_trouble_scroll, # トラブルかどうか
                current_font_object,
                current_scroll_speed,
                current_scroll_interval
            )

    # スクロール停止
    def stop_scrolling(self, task_key):
        # 指定されたインデックスのスクロールを停止
        if task_key in self.scrolling_tasks: # インデックスが存在する場合
            # タスクの構造に合わせてアンパックを調整
            # キーが存在しない場合は None を返す
            task_data = self.scrolling_tasks.pop(task_key, None) # タスク情報を取得
            
            if task_data: # タスク情報が存在する場合
                canvas_widget, text_item_id, _, after_id, _, _, _, _, _, _, _, _ = task_data 
                if after_id: # after_id が存在する場合キャンセル
                    self.after_cancel(after_id) 
                if canvas_widget and text_item_id: # Canvas Widget とテキストアイテムIDが存在する場合
                    try:
                        # タグ名は task_key を含めて統一する
                        canvas_item_tag = str(task_key) + "_text"
                        # find_withtag はアイテムIDのタプルを返す, アイテムIDは数値
                        # text_item_id が canvas_widget.find_withtag(canvas_item_tag) に存在するかを確認
                        if text_item_id in canvas_widget.find_withtag(canvas_item_tag):
                            canvas_widget.delete(text_item_id) # Canvasのアイテムを削除
                    except TclError:
                        pass # エラーが発生しても無視する
    
    # ニュース表示用関数 
    def _scrape_news_headlines(self):
        headlines = []
        try:
            response = requests.get(self.NEWS_URL, timeout = 10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Yahooニュースの主要ニュースのセレクタ(都度調整)
            selectors = [
                'div[data-ual-view-type="list"] li a', # 主要トピックスリスト (2024/05時点の例)
                'a[href*="/pickup/"]', # pickup 記事へのリンク
                'section[data-ylk*="news_topics"] li a' # 別のトピックスセクションの可能性
            ]        
            
            news_elements = []
            for selector in selectors:
                news_elements = soup.select(selector)
                if news_elements:
                    break # 要素が見つかったらループを抜ける
            
            processed_urls = set() # 重複記事を避けるためのセット
            for item in news_elements:
                href = item.get("href", "")
                if href in processed_urls:
                    continue
                
                title = item.get_text(strip=True)
                # aria-label や内部の特定タグからタイトルを取得
                aria_label = item.get("aria-label")
                if aria_label and len(aria_label) > len(title):
                    title = aria_label
                
                # 短すぎたり不要なモノを除外
                if title and len(title) > 8 and not any(kw in title for kw in ["もっと見る","一覧","関連情報"]): 
                    headlines.append(title)
                    processed_urls.add(href)
                if len(headlines) >= 8: # 8件まで
                    break
                
            if not headlines:
                return ["現在、ニュースを取得できません。サイト構造が変更された可能性があります。"]
            return list(dict.fromkeys(headlines)) # 重複を避ける
        except requests.exceptions.RequestException as e:
            print(f"ニュースの取得に失敗しました(ネットワークエラー)：{e}")
            return ["ニュースの取得に失敗しました。(ネットワークエラー)"]
        except Exception as e:
            print(f"ニュースの解析中にエラーが発生しました：{e}")
            return ["ニュースの解析中にエラーが発生しました。"]
        
    # ニュースを更新する関数
    def _update_news_display(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Updating news display called") # debug 呼び出し確認
        if not self.running:
            return
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ニュースを更新します") # debug
        
        headlines = self._scrape_news_headlines()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] News headlines fetched: {len(headlines)} items")
        
        # full_news_text = " ／ ".join(headlines) if headlines else "現在、ニュースを取得できません。"
        news_prefix = "【Yahoo国内ニュース】"
        joined_headlines = " ／ ".join(headlines) if headlines else "現在、ニュースを取得できません。"
        full_news_text = news_prefix + joined_headlines
        
        news_bg_color = "antiquewhite2"
        news_text_color = "black"
        self.news_canvas.configure(bg=news_bg_color)
        self.start_scrolling(
                            self.news_canvas, 
                            full_news_text,
                            self.news_scroll_task_key,
                            text_fill_color=news_text_color,
                            font_object=self.news_font_object,
                            scroll_speed_pixels=1,
                            scroll_interval_ms=40
                            )
    # ニュースの定期更新をスケジュール    
    def schedule_news_updates(self):
        if self.running:
            self._update_news_display() # とりあえず一度更新を実行
            # 次回の更新をスケジュール
            self.after(self.NEWS_UPDATE_INTERVAL_MS, self.schedule_news_updates)
                    
    # 現在時刻を更新する関数
    def update_datetime(self):
        now = datetime.now() # 現在日時
        # 日時をフォーマット
        formatted_datetime = now.strftime("%Y/%m/%d %H:%M:%S" + " 現在 ")
        # ラベルに日時を表示
        self.datetime_label.config(text=formatted_datetime)
        # 1秒ごとに更新
        self.after(1000, self.update_datetime)
    
    # トラブル情報スクロール中か確認
    def is_any_active_trouble_scroll(self, exclude_current_index=None): # 現在のインデックスを除く
        for task_key, task_data in self.scrolling_tasks.items(): # インデックスとタスク情報を取得
            if exclude_current_index is not None and task_key == exclude_current_index:
                continue
            if len(task_data) == 12: # 12要素のタスク情報
                scroll_active = task_data[7] 
                is_trouble = task_data[8] 
                if scroll_active and is_trouble:
                    return True # active なスクロールが見つかれば True を返す
        return False
    
    # 更新を試行
    def try_update_or_defer(self): 
        if self.is_any_active_trouble_scroll(): # トラブル情報スクロール中か確認
            self.update_scheduled_but_pending = True
            print("トラブル情報スクロール中のため, 更新を保留し完了後に試行します。")
        else:
            self.update_train_info_internal() 
            self.update_scheduled_but_pending = False # 実行したので保留解除

    # 定期更新実行
    def schedule_updates(self):
        # 5分ごとに運行情報を更新
        if self.running:
            self.try_update_or_defer() # 更新試行 or 遅延設定
            self.after(300000, self.schedule_updates)  # 5分後に次回のスケジュール 

    # 運行情報を更新する関数
    def update_train_info_internal(self):
        # 現在時刻を取得
        current_time_entry = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        # 呼出確認用ログ
        print(f"現在時刻：{current_time_entry} update_train_info を実行します。") # debug
        if not self.running: # アプリケーションが終了しようとしている場合は何もしない
            return
        try:
            count = 0 
    
            # 登録路線の運行情報を取得
            for item in train_list:
                web_requests = requests.get(url_dict[item]) 
                company_url_to_open = self.railway_company_urls.get(item) # 関連URLを先に取得
                web_requests.raise_for_status() # ステータスコードが4xx or 5xxの場合は例外を発生

                # BeautifulSoupを利用してWebページを解析する
                soup = BeautifulSoup(
                    web_requests.text, 'html.parser')
                
                target_canvas = self.wwt_canvas[count] # 対象の Canvas を先に取得
                icon_widget = self.wwi[count] # 対象のアイコンウィジェット

                # .findでtroubleクラスのddタグを探す
                if soup.find('dd', class_='normal'):
                    status = "normal"
                    trouble_text="平常運転"
                    bg_status_text="AntiqueWhite2" # 通常時の運行情報テキスト背景色
                    # Canvas 背景色を設定し静的テキストを表示
                    # target_canvas はすでに self.wwt_canvas[count] で取得済み
                    target_canvas.configure(bg= bg_status_text)
                    # アイコンの背景色とイベントバインド解除
                    normal_icon_bg = "green yellow" # 通常時のアイコン背景色
                    icon_widget.configure(bg=normal_icon_bg)
                    icon_widget.unbind("<ButtonPress-1>")
                    icon_widget.unbind("<ButtonRelease-1>")
                    self.start_scrolling(
                                        target_canvas,
                                        trouble_text, 
                                        count,
                                        text_fill_color="black",
                                        font_object=self.status_font_object,
                                        is_trouble_scroll=False
                                        )
                else:
                    status = "trouble"
                    trouble_node = soup.find('dd', class_="trouble")
                    original_trouble_text = trouble_node.get_text(separator=' ', strip=True) if trouble_node else "情報取得エラー"
                    # --- ↑↑↑ 三項演算子を使用 ---
                    #
                    # 通常コード ↓↓↓
                    # if trouble_node:
                    #     original_trouble_text = trouble_node.get_text(separator=' ', strip=True)
                    # else:
                    #     original_trouble_text = "情報取得エラー"
                    #
                    # --- ↑↑↑ ここまで ---
                    
                    bg_status_text="yellow" # トラブル時の運行情報テキスト背景色
            
                    target_canvas.configure(bg=bg_status_text) # 背景色を先に設定
                    # アイコンの背景色とイベントバインドの設定
                    trouble_icon_bg = "yellow" # トラブル時のアイコン背景色
                    icon_widget.configure(bg=trouble_icon_bg)
                    if company_url_to_open: # URLが設定されている場合のみクリックイベントをバインド
                        icon_widget.bind(
                                        "<ButtonPress-1>",
                                        lambda e,
                                        iw=icon_widget: self.on_icon_press(iw)
                                        )
                        icon_widget.bind(
                                        "<ButtonRelease-1>",
                                        lambda e,
                                        iw=icon_widget,
                                        url=company_url_to_open,
                                        tn=item,
                                        oib=trouble_icon_bg: self.on_icon_release(iw, url, tn, oib)
                                        )
                    else: # URLが設定されていない場合はイベントバインド解除
                        icon_widget.unbind("<ButtonPress-1>")
                        icon_widget.unbind("<ButtonRelease-1>")
                    
                    # トラブル時の運行情報を赤文字でスクロール表示
                    self.start_scrolling(target_canvas, 
                                         original_trouble_text, 
                                         count,
                                         text_fill_color="red",
                                         font_object=self.status_font_object,
                                         is_trouble_scroll=True
                                         )
                    
                    trouble_text = original_trouble_text # (念のため)
            
                # 路線名の表示
                formatted_item_name = self._format_routename_for_display(item)
                self.wwl[count].configure(text=formatted_item_name)  
                # 区間情報の表示
                section_text = train_section.get(item, "") # train_section から区間情報を取得, なければ空文字列を返す
                self.wws[count].configure(text=section_text) # 念のため
                # 区間ラベルの背景色も路線名に合わせる( create_widgets にて設定済み)
        
                # アイコンの判別
                #current_icon_bg = self.wwi[count].cget("bg") # icon_widget はすでに self.wwi[count] で取得済み
                if status == "trouble": # トラブル発生時は trouble アイコンを使用(優先)
                    icon_widget.configure(image=self.icon_dict["trouble"])
                elif "新幹線" in item: # 路線名に[ 新幹線 ]が含まれていれば
                    # 通常運転時は shinkansen アイコンを使用
                    icon_widget.configure(image=self.icon_dict.get("shinkansen", self.icon_dict["normal"]))
                else: 
                    # 在来線などであれば 従来の処理を実行
                    icon_widget.configure(image=self.icon_dict["normal"])

                # 表示カウンタを更新
                count += 1

        # ネットワークエラーやHTTPエラー
        except requests.exceptions.RequestException as e: 
            print(f"ネットワークエラーまたはリクエストエラーが発生しました：{e}")

        # エラー発生時も次の処理を実行
        except Exception as e: # それ以外のエラー
            print(f"運行情報更新中にエラーが発生しました：{e}")

        # エラー発生時も次の処理を実行
        finally:
        # running が True のみ次の処理( GC とタイマー設定)を実行
            if self.running:
            # コールバック関数を登録
            # 運行状況の更新とメモリ解放を5分毎に実行
                gc.collect() # メモリ解放(ガーベジコレクション)                
                current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                print(f"{current_time} 定期処理を実行しました。 次回は5分後です") # debug
            # threading.Timer(300000, update_train_info_internal).start() # 5分後に再実行

    # プログラム終了処理
    def on_close(self, event=None):
        # ↑↑↑  event引数 デフォルト= None
        print("プログラムを終了します") # debug
        if self.running:
            self.running = False
        # スクロールタスクをすべて停止    
        for index in list(self.scrolling_tasks.keys()):
            self.stop_scrolling(index)
        # ニューススクロールタスクも停止
        if self.news_scroll_task_key in self.scrolling_tasks:
            self.stop_scrolling(self.news_scroll_task_key)
        if sys.platform == "win32" and hasattr(self, "ctypes"):
            try:
                # Windows の場合、ディスプレイのスリープ防止設定を解除
                # (システムのスリープは許可されたまま)
                self.ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            except Exception as e:
                print(f"ディスプレイのスリープ防止設定に失敗しました：{e}") # debug
            self.master.wm_iconify() 
        # ウィンドウを破棄
        self.master.destroy()

    # ウインドウを最大化または元のサイズに戻す
    def toggle_fullscreen(self, event=None):
        self.is_fullscreen_active = not self.is_fullscreen_active
        self.master.attributes("-fullscreen", self.is_fullscreen_active)
        # フルスクリーン解除時は元のウィンドウサイズに戻すことを保証
        if not self.is_fullscreen_active:
            messagebox.showinfo("フルスクリーン解除", "フルスクリーンを解除しました")
            self.master.geometry(self.initial_geometry)
            self.master.resizable(False, False)
        else:
            messagebox.showinfo("フルスクリーン", "フルスクリーンに切り替えました\n解除はRキーまたは再度Fキーを押してください")
        # フルスクリーン変更後、UIの更新を強制、configure イベントを発生させる
        self.master.update_idletasks() 
    
    # ウインドウ最小化    
    def minimize_window(self, event=None):
        self.master.lift()
        self.master.iconify()
        print("ウィンドウを最小化しました") # debug

    # --- ↓↓↓ 使用機器によっては最小化から復元できない ---        
    # def restore_window_from_minimize(self, event=None):
    #     self.master.wm_state("normal")
    #     self.master.focus_force()
    #     print("ウィンドウを(最小化から)復元しました") # debug
    # --- ↑↑↑ ---
        
    # フルスクリーンから元のウィンドウサイズに戻す
    def restore_to_original_size(self, event=None):
        if self.is_fullscreen_active: # full screen であれば解除する
            self.is_fullscreen_active = False
            self.master.attributes("-fullscreen", False)
            messagebox.showinfo("フルスクリーン解除", "フルスクリーンを解除しました") # debug
        else:
            messagebox.showinfo("ウィンドウサイズ", "ウィンドウサイズを元に戻しました") # debug
        self.master.geometry(self.initial_geometry)
        self.master.resizable(False, False) # ウインドウサイズを固定を再確認
        print("ウィンドウサイズを元に戻しました") # debug
        self.master.update_idletasks() # ウィンドウサイズ変更後、UIの更新を強制、configure イベントを発生させる
        
    # 路線名ラベルクリック時のアクション    
    def on_routename_press(self, label_widget, train_name):
        original_style = self.train_styles.get(train_name, {"bg":"lightgray", "fg":"black"}) # self.train_styles を参照
        # クリック時のハイライト背景色(元の文字色が見えるように)
        highlight_bg="lightgray"
        # 元の背景色を維持しつつ背景色を変更する
        label_widget.configure(bg=highlight_bg, fg=original_style["fg"])
    
    # 路線名ラベルクリック解放時のアクション
    def on_routename_release(self, label_widget, url, train_name):
        # 元のスタイルに戻す
        original_style = self.train_styles.get(train_name, {"bg":"lightgray", "fg":"black"}) # fallback
        label_widget.configure(bg=original_style["bg"], fg=original_style["fg"])
        # メッセージボックスで確認
        confirm_open = messagebox.askyesno(
                                            title=f"{train_name}関連リンク確認",
                                            message=f"{train_name}の関連リンクをブラウザで開きますか？？\nURL:{url}"
                                            )
        if confirm_open: # [はい]を選択した場合
            webbrowser.open(url)
            print(f"ブラウザでリンクを開きました:{url}") # debug
        else:
            print(f"キャンセルしました:{url}") # debug
            
    # トラブルアイコンクリック時のアクション
    def on_icon_press(self, icon_label_widget):
        # 背景色を一時的に変更
        icon_label_widget.configure(bg="lightgray")
    
    # トラブルアイコンクリック解放時のアクション
    def on_icon_release(self, icon_label_widget, url, train_name, original_icon_bg):
        # アイコンラベルの背景を元に戻す
        icon_label_widget.configure(bg=original_icon_bg)
        
        if url:
            # メッセージボックスで確認
            comfirm_open = messagebox.askyesno(
                                                title=f"{train_name}関連リンク確認",
                                                message=f"{train_name}の関連リンクをブラウザで開きますか？？\nURL:{url}"
                                                )
            if comfirm_open: # [はい]を選択した場合
                webbrowser.open(url)
                print(f"ブラウザでリンクを開きました:{url}") # debug
            else:
                print(f"キャンセルしました:{url}")
               
    # 保護されていた更新を実行するメソッド
    def _execute_pending_update(self):
        # 保留されていた更新を実行
        if self.running: # アプリケーションが実行中の場合
            self.update_train_info_internal() # 運行情報を更新
                        
# 残りのウィジェット作成( mainframeのcreate_widgets の最後に追加)
def add_news_display_to_mainframe(main_frame_instance: MainFrame):
    num_trains = len(main_frame_instance.wwl) # 運行情報の数を取得
    base_row_for_trains = 2 # 運行情報の表示開始行

    # ニュース表示エリアの上罫線
    news_separator = ttk.Separator(main_frame_instance, orient=HORIZONTAL)
    # 最後の路線の下の罫線の row + 1 に配置
    last_train_content_row = base_row_for_trains + (((num_trains - 1) * 3) + 1 if num_trains > 0 else base_row_for_trains - 1)
    # 最後の路線の下の罫線は last_train_content_row + 1 に配置
    news_separator_row = last_train_content_row + 2
    news_separator.grid(row=news_separator_row, column=0, columnspan=3, sticky="ew", pady=(5,1))
    
    # ニュース表示フレーム
    news_display_row = news_separator_row + 1
    main_frame_instance.news_frame = Frame(main_frame_instance, bg="AntiqueWhite2") # 背景色
    main_frame_instance.news_frame.grid(row=news_display_row, column=0, columnspan=3, sticky="news")
    
    news_font_metrics = main_frame_instance.news_font_object.metrics()
    news_canvas_height = news_font_metrics["ascent"] + news_font_metrics["descent"] + 10 # 余白を追加
    main_frame_instance.news_canvas = Canvas(
                                        main_frame_instance.news_frame,
                                        bg="ivory2",
                                        height=news_canvas_height,
                                        highlightthickness=0
                                        ) # 精一杯, 高さを固定
    main_frame_instance.news_canvas.pack(
                                        fill=X,
                                        expand=False,
                                        padx=10,
                                        pady=5
                                        )
    
    main_frame_instance.rowconfigure(news_separator_row, weight=0)
    main_frame_instance.rowconfigure(news_display_row, weight=0) # ニュース表示フレームの高さを固定
    
    
# メインフレームを配置
app = MainFrame(root) # MainFrame をインスタンス化
app.pack(side=TOP, expand=1, fill=BOTH) # メインフレームを配置
    
# 起動時点で最前面表示
root.attributes("-fullscreen", False) # フルスクリーン解除状態
# ウインドウ"✖"ボタンによる終了
root.protocol("WM_DELETE_WINDOW", app.on_close)
# Qキーによる終了
root.bind("<q>", app.on_close)
# Escキーによる終了
root.bind("<Escape>", app.on_close)
# Fキーによるフルスクリーン
root.bind("<f>", app.toggle_fullscreen)
# Mキーによるウィンドウサイズ最小化
# (タスクバーに格納)
root.bind("<m>", app.minimize_window)

# --- ↓↓↓ 使用機器によっては復元不可(とりあえず残す) ---
# Nキーによるウィンドウ最小化からの復元
# (タスクバーからの復元)
# root.bind("<n>", app.restore_window_from_minimize)
# --- ↑↑↑ ここまで ---

# Rキーによるウィンドウサイズを元に戻す
root.bind("<r>", app.restore_to_original_size)

# 定期更新スケジュール
# 初回起動時はUIが安定するまで少し遅延させてから開始
# サイズ確定後, text 位置が計算され text 表示されるまで少し遅延させる
# 路線情報更新
root.after(100, app.schedule_updates) # 100ミリ秒後に初回更新
# ニュース表示エリアを mainframe に追加
# add_news_display_to_mainframe は mainframe.create_widgets 内で呼び出される
root.after(500, app.schedule_news_updates) # 500ミリ秒後に初回ニュース更新

# メインループ
root.mainloop()
