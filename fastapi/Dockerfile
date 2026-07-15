

FROM python:3.12-slim

#跟我們開一個專案資料夾一樣，我們開一個app資料夾
#等一下全部東西都放裡面
WORKDIR /app

#開始安裝環境
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#建立好環境以後，就會把我們建立的所有程式碼和模版都上傳住/app
#我們整個專案裡面，有些東西是不需要送進雲端的，所以我們需要.dockerignore
COPY . .

ENV PORT=8080

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}

