# coding=utf-8
from imaplib import Literal
import requests
from flask import Flask, request, Response, render_template
from rdflib.namespace import FOAF
from rdflib import Graph, Namespace, RDF
from multiprocessing import Process, Queue
from rdflib.term import Literal
from AgentUtil.ACLMessages import build_message, get_message_properties
import constants.FIPAACLPerformatives as performatives

import constants.FIPAACLPerformatives as FIPAACLPerformatives
import constants.OntologyConstants as OntologyConstants
from AgentUtil import ACLMessages
from orderRequest import OrderRequest
import socket
import time
import uuid
from pedidoRequest import  PedidoRequest
from AgentUtil.Agent import Agent
from string import Template
import random


# Configuration stuff
hostname = '0.0.0.0'
port = 9011
Lote = [] #cada 5 se vacia el lote y se envia


import os
directory_hostname = os.environ['DIRECTORY_HOST'] or hostname

precioBase = 10
precioFinal = 0
app = Flask(__name__, template_folder='./templates')
mensajeFecha = "Recibirás el pedido en 2 dias a partir de:"
precioExtra1 = 0
precioExtra2 = 0

FOAF = Namespace('http://xmlns.com/foaf/0.1/')
agn = Namespace(OntologyConstants.ONTOLOGY_URI)


def update_state(uuid, state):
    print('id:', uuid, 'state:', state)
    all_orders = Graph()
    all_orders.parse('./rdf/database_orders.rdf')
    namespace = Namespace(OntologyConstants.ONTOLOGY_URI)
    order = namespace.__getattr__('order_' + uuid)
    all_orders.set((order, namespace.state, Literal(state)))
    all_orders.serialize('./rdf/database_orders.rdf')
    print(all_orders.serialize(format='xml'))
    return


def crear_lote(prices_eurocents, weights):
    g = Graph()
    g.parse('rdf/database_lotes.rdf')
    all_orders = Graph()
    all_orders.parse('./rdf/database_orders.rdf')
    namespace = Namespace(OntologyConstants.ONTOLOGY_URI)
    lote_uuid = uuid.uuid4()
    nslote = namespace.__getattr__('lote_' + str(lote_uuid))
    g.add((nslote, RDF.type, Literal('ONTOLOGIA_ECSDI/')))
    g.add((nslote, namespace.prices_eurocents, Literal(prices_eurocents)))
    g.add((nslote, namespace.weights, Literal(weights)))
    g.add((nslote, namespace.total_price, Literal(send_pedido(prices_eurocents, weights))))

    query = Template('''
            SELECT DISTINCT ?order ?order_id
            WHERE {
                ?order ns:order_id ?order_id .
                ?order ns:state "$state" .
            }
        ''')
    result_search = all_orders.query(
        query.substitute(dict(state='pending')),
        initNs=dict(
            rdf=RDF,
            ns=agn,
        )
    )
    orders_ids = []
    for order, order_id in result_search:
        print(order_id)
        orders_ids.append(str(order_id))
        #update_state(order_id, 'Looted')
    print('orders ', orders_ids, 'length', len(orders_ids))
    if len(orders_ids) > 5:
        for order_id in orders_ids:
            update_state(order_id, 'Send')
            g.add((nslote, namespace.orders_ids, Literal(orders_ids)))
            g.serialize('./rdf/database_lotes.rdf')
            print('serialized')
    print('not enough for making a loot')
    return


def send_pedido(prices_eurocents, weights):
    prices_eurocents = prices_eurocents[1] + random.randint(0, 50)
    return prices_eurocents



#grafAux = Graph()
#grafAux.parse('./rdf/database_lotes.rdf')
#crear_lote(grafAux, 500, 1000)
#grafAux.serialize('./rdf/database_lotes.rdf')


#update_state('9c3522c4-b425-4a81-b594-9c69ff2f173e', 'pending')
#update_state('7951dc00-ef96-4387-957d-cbc371af7230', 'updated')

cola1 = Queue()


CLAgent = Agent('CLAgent',
                       agn.CLAgent,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % directory_hostname,
                       'http://%s:9000/Stop' % directory_hostname)


def get_prices_weights_from_product_ids(product_ids):
    query = Template('''
        SELECT DISTINCT ?product ?weight_grams ?price_eurocents
        WHERE {
            ?product rdf:type ?type_prod .
            ?product ns:product_id "$product_id" .
            ?product ns:weight_grams ?weight_grams .
            ?product ns:price_eurocents ?price_eurocents .
        }
    ''')

    out = []

    all_products = Graph()
    all_products.parse('./rdf/database_products.rdf')
    for product_id in product_ids:
        result_search = all_products.query(
            query.substitute(dict(product_id=product_id)),
            initNs=dict(
                rdf=RDF,
                ns=agn,
            )
        )

        for product, weight_grams, price_eurocents in result_search:
            item = dict(
                weight_grams=int(weight_grams),
                price_eurocents=int(price_eurocents),
                product_id=product_id
            )
            out.append(item)
    return out


def get_prices_weights_from_orders_graph(graph):

    product_ids = []

    for s, p, o in graph:
        if (p == agn.product_id):
            product_ids.append(str(o))

    print('product ids', product_ids)

    return get_prices_weights_from_product_ids(product_ids)



@app.route("/user_orders", methods=['GET'])
def get_orders():
    all_orders = Graph()
    all_orders.parse('./rdf/database_orders.rdf')

    orders = []
    for db_order in all_orders.subjects(RDF.type, agn.order):
        order = dict(
            order_id=str(all_orders.value(subject=db_order, predicate=agn.order_id)),
            direction=str(all_orders.value(subject=db_order, predicate=agn.direction)),
            cp_code=str(all_orders.value(subject=db_order, predicate=agn.cp_code)),
            status=str(all_orders.value(subject=db_order, predicate=agn.state)),
            product_ids=[],
        )
        for product_id in all_orders.objects(db_order, agn.product_id):
            order['product_ids'].append(str(product_id))
        orders.append(order)

    return render_template('orders.html', orders=sorted(orders, key=lambda k: k['order_id']))


@app.route('/comm', methods=['GET', 'POST'])
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    global precioBase
    global precioFinal
    global mensajeFecha
    global precioExtra1,precioExtra2
    ahora = mensajeFecha
    ahora += " "
    ahora += time.strftime("%c")

    graph = Graph().parse(data=request.data)

    res = get_prices_weights_from_orders_graph(graph)

    print('res is ', res)

    product_prices = [x['price_eurocents'] for x in res]
    product_weights = [x['weight_grams'] for x in res]

    crear_lote(product_prices, product_weights)

    return 'lol'
    #new_order = all_orders.query(query)
    #print(newOrder.serialize(format='xml'))


    print( 'Its a plan request')
    order = OrderRequest.from_graph(graph)
    print('Plan graph obtained, lets construct response message')
   # print(order)
    #if order.peso > 10:
    peso = 11
    #oferta transportista 1
    url ="http://" + hostname + ":" + "9013"+"/calc"
    dataContent = {"peso":peso}
    resp = requests.post(url, data=dataContent)
    precioExtra1 += int(resp.text)
    print("precioExtra = ",precioExtra1)

    #oferta transportista 2
    url ="http://" + hostname + ":" + "9014"+"/calc"
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


def get_new_msg_count():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """

    CLAgent.register_agent(DirectoryAgent)

    pass

if __name__ == '__main__':
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    app.run(host=hostname, port=port)

    ab1.join()
