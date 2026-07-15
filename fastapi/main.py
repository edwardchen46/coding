from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
'''
我們等一下會需要導入靜態檔案資料夾，所以需要staticfiles
甚麼是靜態資料夾，我們說過html需要加css
如果css檔案是獨立的，那我們就會放在靜態資料夾裡面
'''
from fastapi.staticfiles import StaticFiles
'''
jinja2templates就是一人模版程式語言，讓我們可以方便做某部份html碼替換的功能
'''
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Brew & Bean 咖啡廳")

# 將/static路徑綁定到檔案系統的static資料夾，讓前端可以存取靜態檔案（如圖片、CSS、JS等）
# StaticFiles(directory="static")：指定靜態資源的來源資料夾
# name="static"：命名此mount方便後續引用
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MENU_ITEMS = [
    {
        "id": 1,
        "name": "經典拿鐵",
        "category": "咖啡",
        "price": 120,
        "description": "濃郁義式濃縮與綿密奶泡的完美結合",
        "badge": "熱門",
    },
    {
        "id": 2,
        "name": "手沖單品",
        "category": "咖啡",
        "price": 150,
        "description": "每日精選產地豆，風味層次豐富",
        "badge": "推薦",
    },
    {
        "id": 3,
        "name": "冰美式",
        "category": "咖啡",
        "price": 90,
        "description": "清爽冰涼，咖啡香氣十足",
        "badge": None,
    },
    {
        "id": 4,
        "name": "焦糖瑪奇朵",
        "category": "特調",
        "price": 140,
        "description": "香甜焦糖淋醬搭配濃縮咖啡",
        "badge": "新品",
    },
    {
        "id": 5,
        "name": "抹茶拿鐵",
        "category": "特調",
        "price": 130,
        "description": "日本宇治抹茶粉，茶香濃郁",
        "badge": None,
    },
    {
        "id": 6,
        "name": "檸檬氣泡咖啡",
        "category": "特調",
        "price": 135,
        "description": "清新檸檬與氣泡水的夏日驚喜",
        "badge": "季節限定",
    },
    {
        "id": 7,
        "name": "提拉米蘇",
        "category": "甜點",
        "price": 160,
        "description": "經典義式甜點，咖啡與奶油的交響",
        "badge": "熱門",
    },
    {
        "id": 8,
        "name": "可頌",
        "category": "甜點",
        "price": 85,
        "description": "法式酥皮，外脆內軟，每日新鮮出爐",
        "badge": None,
    },
    {
        "id": 9,
        "name": "巴斯克乳酪蛋糕",
        "category": "甜點",
        "price": 140,
        "description": "焦香外皮，內餡濃郁滑順",
        "badge": "推薦",
    },
]

CATEGORIES = ["全部", "咖啡", "特調", "甜點"]

# 這一行是在定義一個用來存放預約資料的清單（reservations），
# 每一個元素都是一個字典（dict），記錄每個預約者的資訊。
reservations: list[dict] = []


# 首頁路由，對 "/" 路徑進行處理，回傳首頁 HTML
# 解釋參數意義：
# - request: FastAPI 的 Request 物件，傳給 Jinja2 模板以取得請求相關資訊（如目前網址，方便切換導覽列 active 狀態）
# - response_class=HTMLResponse: 指定回傳 HTML 頁面格式
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # featured：選出三個有標籤（熱門/推薦/新品）的菜單商品作為首頁精選
    featured = [item for item in MENU_ITEMS if item.get("badge") in ("熱門", "推薦", "新品")][:3]
    # 用 Jinja2 模板渲染 index.html，並傳入 request 物件與精選商品
    ''' 
    網路運作的過程就是一問一答
    user打一個網址進來，我們稱為提出一個request
    針對這個request，fastapi準備相關資料或是html檔案回去，稱為回覆一個response
    下面就開始用模版工具開始準備一個TemplateResponse回覆給user
    '''
    
    return templates.TemplateResponse(
        request,
        "index.html",
        {"featured_items": featured},
    )


@app.get("/menu", response_class=HTMLResponse)
async def menu(request: Request, category: str = "全部"):
    if category != "全部":
        items = [item for item in MENU_ITEMS if item["category"] == category]
    else:
        items = MENU_ITEMS
    return templates.TemplateResponse(
        request,
        "menu.html",
        {"menu_items": items, "categories": CATEGORIES, "active_category": category},
    )


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request, "about.html")


@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request, success: bool = False):
    return templates.TemplateResponse(
        request,
        "contact.html",
        {"success": success},
    )


@app.post("/contact")
async def submit_contact(
    # Form(...) 用在 FastAPI 取得表單欄位資料，等同於 HTTP POST 的 form data。
    # 用 ... （ellipsis）表示這是必填欄位，必須要有值才會通過驗證。
    # 例如 name: str = Form(...) 代表 name 是必填，從前端的 form 拿資料。
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
    guests: int = Form(2),
    date: str = Form(...),
    time: str = Form(...),
):
    reservations.append(
        {
            "name": name,
            "email": email,
            "message": message,
            "guests": guests,
            "date": date,
            "time": time,
        }
    )
    return RedirectResponse(url="/contact?success=true", status_code=303)


@app.get("/api/menu")
async def api_menu():
    return {"items": MENU_ITEMS, "categories": CATEGORIES}
