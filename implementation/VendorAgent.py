# coding=utf-8
from __future__ import print_function
from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph
from flask import Flask, request
import uuid

import constants.FIPAACLPerformatives as performatives
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests
from rdflib import RDF
from rdflib.namespace import FOAF
from AgentUtil.ACLMessages import build_message, get_message_properties


import logging
logging.basicConfig(level=logging.DEBUG)

import random, constants.OntologyConstants as OntologyConstants
from orderRequest import  OrderRequest
from pedidoRequest import  PedidoRequest
from rdflib.term import Literal


# Configuration stuff
hostname = '0.0.0.0'
port = 9012

import os
directory_hostname = os.environ['DIRECTORY_HOST'] or hostname

agn = Namespace(OntologyConstants.ONTOLOGY_URI)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

VendorAgent = Agent('VendorAgent',
                       agn.VendorAgent,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % directory_hostname,
                       'http://%s:9000/Stop' % directory_hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)

import logging
logging.basicConfig(level=logging.INFO)

ns = Namespace('ONTOLOGIA_ECSDI/')
direccions = ["Barcelona", "Valencia", "Madrid", "Zaragoza", "Sevilla", "Tarragona", "Girona", "Lleida", "Castelldefels", "Na macaret"]


@app.route('/comm', methods=['GET', 'POST'])
def comunicacion():
    """
    Entrypoint de comunicacion
    """

    message = request.args['content']
    graph_message = Graph()
    graph_message.parse(data=message)
    message_properties = get_message_properties(graph_message)

    not_understood_message = lambda: build_message(
        Graph(),
        performatives.NOT_UNDERSTOOD,
        sender=VendorAgent.uri,
        msgcnt=get_new_msg_count()
    ).serialize(format='xml')

    if message_properties is None:
        return not_understood_message()

    content = message_properties['content']
    action = graph_message.value(
        subject=content,
        predicate=RDF.type
    )

    if str(action) == OntologyConstants.ACTION_SEND_DEV:
        s = ""
        # aqui devolucion
        ran = random.randint(0, 9)
        if ran > 6:
            return "devolución denegada por la tienda"
        return "devolución aceptada"
    elif str(action) == OntologyConstants.ACTION_CREATE_ORDER:
        return create_order(graph_message).serialize(format='xml')
    elif str(action) == OntologyConstants.ACTION_ADD_EXT:
        return create_product(graph_message)
    else:
        return not_understood_message()



def create_product(graph_message):
    print(graph_message.serialize(format='xml'))
    nombreProducto = marca = seller = category = description = ""
    idProducto = importe = peso = 0
    for s,p,o in graph_message:
        if str(p) == "http://ONTOLOGIA_ECSDI/seller":
            seller = str(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/product_description":
            description = str(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/price_eurocents":
            importe = int(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/product_id":
            idProducto = str(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/product_name":
            nombreProducto = str(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/weight_grams":
            peso = int(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/category":
            category = str(o)
        elif str(p) == "http://ONTOLOGIA_ECSDI/brand":
            marca = str(o)
    print("seller = ",seller)
    print("seller2 = ",str(seller))
    print(seller,description,importe,idProducto,nombreProducto,peso,category,marca)
    print("Llegim graph productes dintre del if 55555")
    all_orders = Graph()
    all_orders.parse('./rdf/database_products.rdf')
    print("Afegim producte")
    add_product(all_orders, nombreProducto, idProducto, importe, marca, peso, seller, category, description)
    print("Sobreescrivim base de dades de productes")
    all_orders.serialize('./rdf/database_products.rdf')

    return graph_message.serialize(format='xml')

def create_order(graph_message):
    all_orders = Graph()
    try:
        all_orders.parse('./rdf/database_orders.rdf')
    except:
        print('Cannot read existing order database. Creating new one.')
    subject = None
    for s, p, o in graph_message:
        if str(s).startswith(str(agn['order_'])) == False:
            continue
        if p == RDF.type:
            subject = s
            all_orders.add((s, p, agn.order))
        else:
            all_orders.add((s, p, o))
    all_orders.add((subject, agn.cp_code, Literal(random.randint(1, 9999))))
    all_orders.add((subject, agn.direction, Literal(direccions[random.randint(0, 9)])))
    all_orders.add((subject, agn.state, Literal('pending')))
    all_orders.serialize('./rdf/database_orders.rdf')

    CLAgent = VendorAgent.find_agent(DirectoryAgent, agn.CLAgent)

    message = build_message(
        graph_message,
        Literal(performatives.REQUEST),
        Literal(OntologyConstants.SEND_PEDIDO)
    ).serialize(format='xml')

    resp = requests.post(CLAgent.address, data=message)

    return resp

def add_order(g, order_id, product_ids, uuid, peso, cp_code, direction, state):
    namespace = Namespace(OntologyConstants.ONTOLOGY_URI)
    order = namespace.__getattr__('#RequestOrder#' + str(order_id))
    g.add((order, RDF.type, Literal('ONTOLOGIA_ECSDI/order')))
    g.add((order, namespace.uuid, Literal(uuid)))
    g.add((order, namespace.cp_code, Literal(cp_code)))
    g.add((order, namespace.direction, Literal(direction)))
    g.add((order, namespace.weight_grams, Literal(peso)))
    g.add((order, namespace.state, Literal(state)))
    for product_id in product_ids:
        g.add((order, namespace.product_id, Literal(product_id)))


def get_new_msg_count():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def add_product(g, nombreProducto, idProducto, importe, marca, peso, seller, category, description):
    namespace = Namespace(OntologyConstants.ONTOLOGY_URI)
    product = namespace.__getattr__('#AddExternal#' + str(idProducto))
    g.add((product, RDF.type, Literal('ONTOLOGIA_ECSDI/')))
    g.add((product, namespace.price_eurocents, Literal(importe)))
    g.add((product, namespace.category, Literal(category)))
    g.add((product, namespace.seller, Literal(seller)))
    g.add((product, namespace.product_name, Literal(nombreProducto)))
    g.add((product, namespace.product_description, Literal(description)))
    g.add((product, namespace.brand, Literal(marca)))
    g.add((product, namespace.weight_grams, Literal(peso)))

def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    VendorAgent.register_agent(DirectoryAgent)
    pass

if __name__ == '__main__':
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    app.run(host=hostname, port=port)

    ab1.join()