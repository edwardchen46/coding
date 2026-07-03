for i in [3,7,23]:
    print(f"現在讀到的數字是{i}")
    
total_3=0
total_5=0
total_35=0
for i in range(1,101):
    if i%3==0:
        total_3=total_3+i
    if i%5==0:
        total_5=total_5+i
    if i%3==0 and i%5==0:
        total_35=total_35+i
        
print(f'1到100,3的倍數加總是{total_3}')
print(f'1到100,5的倍數加總是{total_5}')
print(f'1到100,3和5的倍數加總是{total_35}')