

from fastapi import FastAPI
# 建立 FastAPI 應用實例
app = FastAPI(title="我的第一個 FastAPI")
'''
網站溝通需要有不同的動作設定
get就是最常使用的動作
fastapi現在很像站在路發傳單
路人走過來，get一張，就給你一個網頁
透過app.get('/')就是代表
user用http://127.0.0.1:8000/ 就會連到這個function
http://127.0.0.1:8000  就是我的首頁網址

在fastapi 裡面每個function都會設計成async，非同歩作業
你把fastapi想像成餐廳的服務生
他去了A桌，請問點甚麼，客人在想
所以就說你想好叫我，就換去B桌點餐
'''
@app.get("/")
async def home():
         """首頁：回傳簡單的 JSON
            你會說return明明是是一個dict，怎麼會是json
            json是網路世界共通的資料結構
            要把一個dict傳出去之前都會轉成json
            這個轉的動作，fastapi也幫你做完了
         """
         return {"message": "Hello, 這是第一個fastapi連進來的網址!"}

'''
https://search.books.com.tw/search/query/key/python/cat/all
從博客來網址的變換，你可以看到你的需求，會透過網址的變換來傳遞參數
/hello/{name} {}的部份就是要說明路徑的這個部份會是一個參數
name是你自己取的變是，等一下用這個
'''

#'http://127.0.0.1:8000 /hello/Diana'
@app.get("/hello/{name}")
async def hello(name: str):
        """路徑參數：把 URL 中的 name 帶進來"""
        return {"message": f"你好，{name}！"}

'''
我們的參數來自兩個部份
第一個部份跟上面一樣，
'''
@app.get("/items")
async def list_items(limit: int = 10):
        """查詢參數：例如 /items?limit=3"""
        items = ["拿鐵", "美式", "卡布奇諾", "摩卡", "可頌"]
        return {"items": items[:limit]}