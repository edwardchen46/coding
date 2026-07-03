# # # # # # # a=[]

# # # # # # # for i in range(1,6):
# # # # # # #     c=int(input("請輸入數字"))
# # # # # # #     a.append(c)

# # # # # # # print(f"{a[2]}+{a[3]}+{a[4]}=",a[2]+a[3]+a[4])

# # # # # # a=int(input("請輸入數字"))
# # # # # # b=int(input("再輸入一次"))
# # # # # # result=0
# # # # # # for i in range(a,b+1):
# # # # # #     if i%2==0:
# # # # # #         result=result+i

# # # # # # print(result)

# # # # # for i in range(1, 10):
# # # # #     for j in range(1, 10):
# # # # #         result = i * j
# # # # #         print(f"{i}*{j}={result:<3d}", end=" ")
# # # # #     print()         # 換列輸出
    
# # # # for i in range(20):
# # # #     if i in [7,9,11]:
# # # #         continue
# # # #     else:
# # # #         print(i)

# # # # ch7_26.py
# # # msg1 = '人機對話專欄,告訴我心事吧,我會重複你告訴我的心事!'
# # # msg2 = '輸入 q 可以結束對話'
# # # msg = msg1 + '\n' + msg2 + '\n' + '= '
# # # input_msg = ''                  # 預設為空字串
# # # # while input_msg != 'q':
# # # #     input_msg = input(msg)
# # # #     if input_msg != 'q':        # 如果輸入不是q才輸出訊息         
# # # #         print(input_msg)

# # # while True:
# # #     input_msg=input(msg)
# # #     if input_msg=='q':
# # #         break
# # #     else:
# # #         print(input_msg)

# # # ch7_37.py
# # scores = [21,29,18,33,12,17,26,28,15,19] 
# # # 解析enumerate物件
# # for count, score in enumerate(scores, 1):   # 初始值是 1
# #     if score >= 20:
# #         print(f"場次 {count} : 得分 {score}")
# l = []
# while True:
#     n = eval(input())
#     if n == 9999: break
#     l.append(n)
# print(min(l))

while True:
    y = eval(input())
    if y == -9999: break
    if y % 4 == 0 and y % 100 != 0 or y % 400 == 0:
        print(f'{y} is a leap year.')
    else:
        print(f'{y} is not a leap year.')