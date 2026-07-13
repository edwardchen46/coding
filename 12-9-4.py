# ch12_9_4.py
class Score():
    def __init__(self, score,gender):
        self.__score = score
        self.__gender= gender

    # @property就是裝飾器
    # 下面明明是一個function上面加上一個@property就會變成類似屬性的東西
    @property
    def sc(self):
        print("inside the getscore")
        # 現在這個sc就是給你這個物件內部的_score
        # 所以我們說sc就是_score的getter，可以讓外部取得這個內部值
        return self.__score
    @sc.setter
    # 取一個同名，都叫sc的method，裝飾上@sc.setter
    # 名為setter，就是要重新賦值，給一個新的東西
    def sc(self, score):
        print("inside the setscore")
        self.__score = score    
    
    @property
    def abc(self):
        return self.__gender
    @abc.setter
    def abc(self,value):
        if value in ['F','M','f','m']:
            self.__gender =value.upper()
        else:
            print('輸入內容不被接受')

# 用零分先做一個物件出來
stu = Score(0,'m')
# 現在透過過.sc就可以把_score叫出來
print(stu.sc)
print(stu.gender)
stu.sc = 80
print(stu.sc)







        
        
