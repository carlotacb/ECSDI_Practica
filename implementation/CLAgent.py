from imaplib import Literal
import requests
from flask import Flask, request, Response
from rdflib import Graph

import FIPAACLPerformatives
import OntologyConstants
from AgentUtil import ACLMessages
from orderRequest import OrderRequest
import socket
import time


# Configuration stuff
hostname = socket.gethostname()
port = 9011
Lote = [] #cada 5 se vacia el lote y se envia

precioBase = 10
precioFinal = 0
app = Flask(__name__)
mensajeFecha = "Recibirás el pedido en 2 dias a partir de:"
precioExtra1 = 0
precioExtra2 = 0

@app.route('/comm', methods=['GET', 'POST'])
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    print("here CLAgent comunicacion")
    graph = Graph().parse(data=request.data)
    global precioBase
    global precioFinal
    global mensajeFecha
    global precioExtra1,precioExtra2
    ahora = mensajeFecha
    ahora += " "
    ahora += time.strftime("%c")
    print( 'Its a plan request')
    order = OrderRequest.from_graph(graph)
    print('Plan graph obtained, lets construct response message')
   # print(order)
    #if order.peso > 10:
    peso = 11

    #oferta transportista 1
    url ="http://" + hostname + ":" + "9012"+"/calc"
    dataContent = {"peso":peso}
    resp = requests.post(url, data=dataContent)
    precioExtra1 += int(resp.text)
    print("precioExtra = ",precioExtra1)

    #oferta transportista 2
    url ="http://" + hostname + ":" + "9013"+"/calc"
    dataContent2 = {"size":len(Lote)}
    resp = requests.post(url, data=dataContent2)
    precioExtra2 += int(resp.text)
    print("precioExtra = ", precioExtra2)

    Lote.append(order.product_id)
    LoteFinal = Lote[:]
    if len(Lote) == 5 :
        #realizar envio
        #vaciar lote
        precioFinal = min(precioExtra2,precioExtra1)
        precioBase = 10
      #  LoteFinal[:] = Lote[:]
        Lote[:] = []
        LoteFinal.append(ahora)
        LoteFinal.append(precioFinal)
        precioExtra1 = precioExtra2 = 0
        print(ahora)
        print(LoteFinal)
        return str(LoteFinal)

    return len(Lote).__str__()
    return order.product_id


if __name__ == '__main__':
    app.run(host=hostname, port=port, debug=True)