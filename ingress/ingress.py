from http import client
import socket
import queue

from pkg_resources import ContextualVersionConflict
import protocol_lib
import multiprocessing

def message_from_client(message, address, workers, clients, workersInUse, lockWorkers, lockClients, lockWorkersInUse):
    if address in clients:
        clientIndex = clients.index(address)
    else:
        lockClients.acquire()
        clients.append(address)
        lockClients.release()
        clientIndex = len(clients)-1

    # If the file has been successfully received, add worker back to main queue
    if message[protocol_lib.actionSelectorIndex] & protocol_lib.fileAckMask == protocol_lib.fileAckMask:
        lockWorkersInUse.acquire()
        worker = workersInUse.pop(clientIndex)
        lockWorkersInUse.release()

        lockWorkers.acquire()
        workers.put(worker)
        lockWorkers.release()
        return

    if clientIndex not in workersInUse:
        worker = workers.get(block=True, timeout=None) # If there is no worker currently available, block until there is
        lockWorkersInUse.acquire()
        workersInUse[clientIndex] = worker
        lockWorkersInUse.release()

    else:
        worker = workersInUse[clientIndex]

    bytesToSend = message[0:protocol_lib.clientIndex] + clientIndex.to_bytes(1, 'big') + message[protocol_lib.clientIndex+1:]
    UDPServerSocket.sendto(bytesToSend, worker)

def message_from_worker(message, address, workers, clients, lockWorkers):
    # If message is a declaration from worker
    if message[protocol_lib.actionSelectorIndex] & protocol_lib.declarationMask == protocol_lib.declarationMask:
        msg = "Worker declared: {}".format(message)
        IP = "Worker IP address: {}".format(address)
        print(msg)
        print(IP)
        lockWorkers.acquire()
        workers.put(address)
        lockWorkers.release()
        return

    # Message is from worker but is not a declaration
    client = message[protocol_lib.clientIndex]
    # Sending the reply to the client,
    UDPServerSocket.sendto(message, clients[client])

def deal_with_recv(bytesAddressPair, workers, clients, workersInUse, lockWorkers, lockClients, lockWorkersInUse):
    message = bytesAddressPair[0]
    address = bytesAddressPair[1]

    # if message is from client
    if message[protocol_lib.actionSelectorIndex] & protocol_lib.fromClientMask == protocol_lib.fromClientMask:
        message_from_client(message, address, workers, clients, workersInUse, lockWorkers, lockClients, lockWorkersInUse)

    # if message is from worker
    elif message[protocol_lib.actionSelectorIndex] & protocol_lib.fromWorkerMask == protocol_lib.fromWorkerMask:
        message_from_worker(message, address, workers, clients, lockWorkers)


# Main contents:

localIP = ""
localPort = protocol_lib.ingressPort
manager = multiprocessing.Manager()
workers = manager.Queue()
clients = manager.list()
workersInUse = manager.dict()
lockWorkers = manager.Lock()
lockClients = manager.Lock()
lockWorkersInUse = manager.Lock()

# Create a UDP socket
UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

# Bind socket to IP and port
UDPServerSocket.bind((localIP, localPort))

print("UDP ingress server up and listening")

# Listen for incoming messages
while True:
    bytesAddressPair = UDPServerSocket.recvfrom(protocol_lib.bufferSize)

    process = multiprocessing.Process(target=deal_with_recv,args=(bytesAddressPair,workers,clients, workersInUse, lockWorkers, lockClients, lockWorkersInUse))
    process.start()
