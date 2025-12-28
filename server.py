import socket
import threading, getopt, sys, string

import datetime
import requests
import logging

# 设置默认的最大连接数和端口号，在没有使用命令传入参数的时候将使用默认的值
LIST = 5
PORT = 7777 # Server端开放的服务端口
BUFFSIZE = 1024

HOST = ''  # 定义侦听本地地址口（多个IP地址情况下），''表示侦听所有
request_URL = 'http://192.168.1.122:7777/api/device/v1/scan_qrcode'



SUCCESS = 'code=0000'
FAILURE = 'code=0001'


def handle(client, address):
    is_heartbeat = 0
    new_connection = 1
    device_ip = address[0]
    device_id = ""

    while True:
        try:
            # 设置超时时间
            client.settimeout(1000)
            # 接收数据的大小
            tcp_data = client.recv(BUFFSIZE).decode('utf-8')
            print("tcp_data:", tcp_data)
            if not tcp_data:
                print("connection lost:", device_ip)
                break

            if 'vgdecoderesult' in tcp_data:        # 扫码/刷卡数据vgdecoderesult=xx&&devicenumber=xx&&otherparams=
                is_heartbeat = 0
                http_req = tcp_data
            else:                                   # 心跳包
                is_heartbeat = 1
                if new_connection:                  # 首次通信，注册IP
                    http_req = tcp_data + ':' + device_ip
                    device_id = tcp_data
                    new_connection = 0
                else:
                    http_req = tcp_data

            http_data = requests.post(url=request_URL, data=http_req)
            http_data.encoding = 'utf-8'
            res = http_data.text
            if not is_heartbeat:                   # 返回开门请求结果
                print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S "), 'DoorRequest:', http_req, '>>>', res)
                if SUCCESS in res:
                    client.send(SUCCESS.encode())
                else:                # FAILURE in res
                    client.send(FAILURE.encode())
            else:
                print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S "), 'Heartbeat:', http_req, '>>>', res)

        # 超时后显示退出
        except socket.timeout:
            print("Heartbeat time out:", device_ip)
            break
    # 关闭与客户端的连接
    print("Client close:", device_id, ":", device_ip)
    logging.warning("Client close:" + device_id + ":" + device_ip)
    client.close()


def main():
    logging.basicConfig(level=logging.DEBUG,  # 控制台打印的日志级别
                        filename='device.log',
                        filemode='a',  # 模式，有w和a，w就是重写模式，a是追加模式，默认是追加模式
                        format='%(asctime)s - %(levelname)s: %(message)s'  # 日志格式
                        )

    # 创建socket对象。调用socket构造函数
    # AF_INET为ip地址族，SOCK_STREAM为流套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # 将socket绑定到指定地址，第一个参数为ip地址，第二个参数为端口号
    sock.bind((HOST, PORT))
    # 设置最多连接数量
    sock.listen(LIST)
    while True:  
        # 服务器套接字通过socket的accept方法等待客户请求一个连接
        client, address = sock.accept()
        print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S "), 'New door_controller connection from', address)
        logging.warning('New door_controller connection from' + address[0])
        thread = threading.Thread(target=handle, args=(client, address))
        thread.start()


if __name__ == '__main__':
    print(PORT)
    main()
