
mylist = ['vineperf', 'spirent']
test = 'spirent'
if all(x not in test for x in mylist):
    print('Hello')
