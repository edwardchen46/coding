'''
# ch5_7.py
print("計算最終成績")
score = input("請輸入分數 : ")
sc = int(score)
if (sc >= 90):
    print(" A")
elif (sc >= 80):
    print(" B")
elif (sc >= 70):
    print(" C")
elif (sc >= 60):
    print(" D")
else:
    print(" F")
    


a=int(input("請輸入一個數字"))

if a%3==0 and a%5==0:
    print(f"{a}是3和5的倍數")
elif a%3==0:
    print(f"{a}是3的倍數")
elif a%5==0:
    print(f"{a}是5的倍數")
else:
    print(f"{a}不是3和5的倍數")

# 使用者輸入身高(公分)和體重(公斤)
height = float(input("請輸入身高(公分)："))
weight = float(input("請輸入體重(公斤)："))

# 將身高換算成公尺
height = height / 100


# 判斷體重狀況
if bmi:= weight / (height ** 2)> 28:
    print("過重")
elif bmi < 16:
    print("太輕")
else:
    print("正常")


import random
result=random.randint(1,6)
if result>3:
    print(f"骰子擲出{result}是為大")
elif result==3:
    print(f"骰子擲出{result}是通殺")
else:
    print(f"骰子擲出{result}是為小")
'''

import random

# 使用 eval() 函數來解析使用者輸入的表達式，這可能帶來安全風險，
# 因此這裡改用 int() 函數直接將輸入轉換為整數。
user = int(input('輸入1是剪刀，2是石頭,3是布：'))

# 確保使用者輸入的是有效的選項
if user not in [1, 2, 3]:
    print("無效的選擇，請輸入1、2或3。")
else:
    # 使用 random.randint() 函數來生成電腦的選擇
    com = random.randint(1, 3)
    
    # 創建一個字典來對應選擇的名稱
    choices = {1: '剪刀', 2: '石頭', 3: '布'}
    
    print(f"使用者選擇了：{choices[user]}")
    print(f"電腦選擇了：{choices[com]}")
    
    # 比較兩個選擇並判斷獲勝者
    if user == com:
        print("平局！")
    elif (user == 1 and com == 3) or (user == 2 and com == 1) or (user == 3 and com == 2):
        print("使用者獲勝！")
    else:
        print("電腦獲勝！")
