from multiprocessing import Process
from queue import Queue

from flask import Flask, request, Response


import socket
hostname = '0.0.0.0'
port = 9014
app = Flask(__name__)


@app.route('/calc', methods=['GET', 'POST'])
def calculaPreu():
    print("request form : ")
    print(request.form.get("size"))
    data = request.form.get("size")
    extra = data*2
    return str(extra)

if __name__ == '__main__':
    app.run(host=hostname, port=port)
