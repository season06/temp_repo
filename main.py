from functools import lru_cache

class Test:
    def __init__(self):
        pass

    def execute(self):
        print('test')

@lru_cache(maxsize=None)
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

def get_name() -> str:
    return 'world'

def hello(name) -> None:
    if not name:
        name = get_name()
        
    fibonacci(5)

    test = Test()
    test.execute()

    print(f'hello, {name}')

if __name__ == "__main__":
    hello('')
    hello('season')