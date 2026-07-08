# 
total=[]
while True:
    
    s=input("請輸入數字")
    if s.isdigit():
        total.append(int(s))
    else:
        break

if not total:
    print("list裡沒有值")
else:
   print(total)
