# # d = dict()
# # while True:
# #     key = input('Key: ')
# #     if key == 'end': break
# #     value = input('Value: ')
# #     d[key] = value
# # k = input('Search key: ')
# # print(k in d)

# dict_1 = dict()
# dict_2 = dict()
# print('Create dict1:')
# while True:
#     key = input('Key: ')
#     if key == 'end': break
#     dict_1[key] = input('Value: ')
# print('Create dict2:')
# while True:
#     key = input('Key: ')
#     if key == 'end': break
#     dict_2[key] = input('Value: ')
# dict_1.update(dict_2) # 也可以寫成: d = dict_1 | dict_2
# for k, v in sorted(dict_1.items()):
#     print(f'{k}: {v}')
a={}
b={}
print('create dict1:')
while True:
    key=input('key:')
    if key=='end':
        break
    else:
        value=input('value:')
        a[key]=value

print('create dict2:')
while True:
    key=input('key:')
    if key=='end':
        break
    else:
        value=input('value:')
        b[key]=value

c=a|b

for i in sorted(c.keys()):
    print(f'{i}:{c[i]}')
