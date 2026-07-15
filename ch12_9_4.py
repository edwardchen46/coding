class Score():
    # __init__就是class的初始化function
    def __init__(self, score):
        self.__score = score

    # 　@property 就是裝飾器
    #　下面明明是一個function，上面加上一個@property就會變成類似屬性的東西
    #  sc這個名字是你自己取的  記得  三位一體  名字要一致
    @property
    def kitty_sc(self):
        print("inside the getscore")
        # 現在這個sc就是給你這個物件內部的__score
        # 所以我們說sc就是__score的getter  可以讓外部取得這個內部值
        return self.__score

    @kitty_sc.setter
    #　取一個同名，都叫sc的method  裝飾上@sc.setter
    #  名為setter 就是要重新賦值  給一個新的東西
    def kitty_sc(self, score):
        print("inside the setscore")
        if score>=0 and score<=100:
             print(123)
             self.__score = score 
        else:
            print('成績太奇怪了，不給你改')   

# 用零分先做一個物件出來   
stu = Score(0)
# 現在透過.sc就可以把__score叫出來
print(stu.kitty_sc)
stu.kitty_sc = -80
print(stu.kitty_sc)







        
        
