import ast
text = open('main.py', 'r', encoding='utf-8').read()
try:
    ast.parse(text)
    print('Parsed OK')
except Exception as e:
    print(type(e), e)
    import traceback
    traceback.print_exc()
