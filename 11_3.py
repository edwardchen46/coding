def process(data):
    return len(data),sum(data),sum(data)/len(data)

a=[11,13,5,6,18]

num,add_rerult,avg_result=process(a)
print(f"裡面有{num}個值，加總結果是{add_rerult},平均是{avg_result}")