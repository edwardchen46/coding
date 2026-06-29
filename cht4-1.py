'''
print()就是一個函式
()這就是投料孔，它就是一個控制print()怎麼運作的入口
()投料孔裡放的就是參數(參考的數值讓print參考怎麼去運作)
sep就是seperator分隔符號，你希望輸出多個東西的時候，中間要用甚麼分隔符號
sep有設定就用你設定的，沒設定會有預設值，預設值是空格

# ch4_24.py
fobj1 = open("out24w.txt", mode="w")   # 取代先前資料
print("Testing mode=w, using utf-8 format", file=fobj1)
fobj1.close( )
fobj2 = open("out24a.txt", mode="a")   # 附加資料後面
print("測試 mode=a 參數, 預設 ANSI 編碼", file=fobj2)
fobj2.close( )
'''
with open("out24a.txt", "a", encoding="utf-8") as f:
    print("寫得進去嗎",file=f)


