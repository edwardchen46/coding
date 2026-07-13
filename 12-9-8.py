# ch12_9_8.py
class Father():
    def hometown(self):
        print('我住在台北')

    
class Son(Father):
    def eat(self):
        print('我們家愛吃牛肉麵')

hung = Father()
ivan = Son()
hung.hometown()
ivan.hometown()

ivan.eat()




