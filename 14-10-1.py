import os

file_folder='data'
pos='data/file.txt'
if os.path.exists(file_folder):
    print(f"{file_folder}已經存在")
else:
    os.mkdir(file_folder)

with open(pos,'a',encoding='utf-8')as file:
    file.write('今天是星期一\n')
    