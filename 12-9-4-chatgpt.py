class Score:
    def __init__(self, score, gender):
        # 私有屬性
        self.__score = score
        self.__gender = gender.upper()

    # score 的 getter
    @property
    def score(self):
        print("inside the getscore")
        return self.__score

    # score 的 setter
    @score.setter
    def score(self, value):
        print("inside the setscore")
        self.__score = value

    # gender 的 getter
    @property
    def gender(self):
        return self.__gender

    # gender 的 setter
    @gender.setter
    def gender(self, value):
        if value.upper() in ['M', 'F']:
            self.__gender = value.upper()
        else:
            print("輸入內容不被接受")


stu = Score(0, 'm')

print(stu.score)
print(stu.gender)

stu.score = 80
stu.gender = 'f'

print(stu.score)
print(stu.gender)