# b=[]
# for i in range(5):
#     b.append(int(input("請輸入整數")))

# sum=0
# sum1=0
# sum10=0
# for  j in b:
#     if j%2 ==0:
#         sum+=j
#     elif j%2 !=0:
#         sum1+=j
#     if j>10:
#         sum10+=j

# print(f"所有偶數和為{sum}")
# print(f"所有奇數和為{sum1}")
# print(f"所有大於10的和為{sum10}")

# name=['jeff','sandy','jack']
# en=[90,92,45]
# print(list(zip(name,en)))

data={
    'name':'jeff',
    'en':90,
    'math':60,
    'ch':80
}

print(f"{data['name']}的名字")
for name,team in data.items():
    print(name,team)
    