import logging
import multiprocessing
import threading
import time
import tkinter
from tkinter import ttk

import netmiko.exceptions

import xlrd
from netmiko import ConnectHandler, Netmiko
import textfsm
import os
import datetime
from tkinter import messagebox

import tkinter.filedialog
import csv
import chardet

import queue
from concurrent.futures import ThreadPoolExecutor
import threading

logging.basicConfig(filename='uptklog.log', level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(message)s', datefmt='%Y-%m-%d %X')


def get_encoding(file):
    # 二进制方式读取，获取字节数据，检测类型
    with open(file, 'rb') as f:
        return chardet.detect(f.read())['encoding']


masterKey = ["Shelf", "Slot", "PowerName", "State"]
msgqueue = queue.Queue()
devqueue = queue.Queue()
def getMasterNode(argList):
    global masterKey
    for i in argList:
        beginNode = i[0]
        if "*" in beginNode:
            print("find master node =%s" % i)
            masterData = [i[0], i[1], i[4], i[5]]
            return dict(zip(masterKey, masterData))
    return None


def getIndexNode(argList, slotid):
    global masterKey
    for i in argList:
        PowerName = i[4]
        Begin = i[0]
        print('i={}  i[1]=[{}] slotid=[{}]'.format(i,str(i[1]).lstrip() ,slotid))
        if str(i[1]).lstrip() == str(slotid):
            print('card 1= {} match soltid={}'.format(i[1],slotid))
            masterData = [i[0], i[1], i[4], i[5]]
            return dict(zip(masterKey, masterData))
    print('card 1= {} not match soltid={}'.format(i[1], slotid))
    return None


def getBackNode(argList):
    global masterKey
    for i in argList:
        PowerName = i[4]
        Begin = i[0]
        if "NXU" in PowerName and "*" not in Begin:
            print("find back node =%s" % i)
            masterData = [i[0], i[1], i[4], i[5]]
            return dict(zip(masterKey, masterData))
    return None

class msgobj():
    def __init__(self,text,**rowdata):
        print('init obj={}'.format(rowdata))
        self.deviceip = rowdata['网元ip']
        self.slotid = rowdata['solt id']
        self.powername = rowdata['PowerName']
        self.upfilename = ""
        self.text = text
        self.outinfo = ""
        self.resultText = ""
        self.cardinfo = rowdata
        self.cardbootromRes = ""
        self.cardsoftwareRes = ""
        self.cardfpgaRes = ""
        self.cardcpldRes = ""
        

    def bootromRes(self,resultText):
        self.cardbootromRes = resultText
    def softwareRes(self,resultText):
        self.cardsoftwareRes = resultText
    def fpgaRes(self,resultText):
        self.cardfpgaRes = resultText
    def cpldRes(self,resultText):
        self.cardcpldRes = resultText
    def finnalRes(self,resultText):
        self.cardbootromRes = resultText
        self.cardsoftwareRes = resultText
        self.cardfpgaRes = resultText
        self.cardcpldRes = resultText

    def outtext(self,outmsg,card=False):
        self.resultText = outmsg
        if self.upfilename == "" or card == True:
            self.text.insert('end', '\n {} 设备:{} slotid:{} {}  {}'.format(str(datetime.datetime.now()),
                                                                                    self.deviceip, self.slotid,self.powername,
                                                                                      outmsg))
        else:
            self.text.insert('end', '\n {} 设备:{} slotid:{} {} 版本文件:{} {}'.format(str(datetime.datetime.now()),self.deviceip,self.slotid,self.powername,
                                                                                       self.upfilename,  outmsg))
        self.outinfo = ""
    def addmsg(self,msg):
        self.outinfo = "{} {} \n ".format(self.outinfo,msg)
        self.resultText = msg

    def outmsg(self):

        out = "{} {}".format(datetime.datetime.now(),self.outinfo)
        self.outinfo = ""
        return  out
    def setupfilename(self,filename):
        self.upfilename = filename

def getrowdata(kname, rowdata):
    getvalue = rowdata.get(kname)
    if getvalue is not None:
        if len(str(getvalue).strip()) == 0:
            return None
    return getvalue


def task(rowData):
    global g_model,msgqueue
    print('in task rowdata=',rowData)
    dev_info = {
        'device_type': 'raisecom_telnet',
        'ip': str(rowData['网元ip']),
        'username': str(rowData['用户名']),
        'password': str(rowData['密码']),
        'secret': str(rowData['密码']),
        'session_log': 'netmiko.log',
        'port': int(rowData['端口号']),
    }
    print('begin send queue')
    outmsg = msgobj(text,**rowData)
    outmsg.outtext('开始升级')
    print('end send queue')
    needreboot = True
    uploadsucess = False
    try:
        print('begin connect {}'.format(dev_info))
        try:
            net_connect = ConnectHandler(**dev_info)
        except Exception:
            net_connect = reconnect(3,3,dev_info)
            if net_connect is None:
                print('连接设备失败')
                outmsg.outtext('连接设备失败')
                outmsg.finnalRes('连接设备失败')
                msgqueue.put(outmsg)
                return '连接设备失败'
        net_connect.enable()
        masterInfo = None
        backInfo = None
        command = "show card"
        onemaster = False
        resetFlag = False
        cardsate =""
        cardinfo = net_connect.send_command(command)
        with open('template/showcard.template') as template:
            fsm = textfsm.TextFSM(template)
            result = fsm.ParseText(cardinfo)
            masterInfo = getMasterNode(result)
            backInfo = getBackNode(result)
            cardsate = result[0][5]
        print('板卡状态={}'.format(cardsate))
        print('开始处理 检查主备板卡 master={} backinfo={}'.format(masterInfo,backInfo))
        if cardsate != 'working':
            outmsg.outtext('板卡状态不是working状态，无法升级请检查')
            outmsg.finnalRes('板卡状态不是working状态，无法升级请检查')
            msgqueue.put(outmsg)
            return '板卡状态不是working状态，无法升级请检查'

        if rowData['板卡属性'] == '主控板':
            print('主控板开始升级。。。。')

            masterSoltId = rowData.get('solt id').strip()
            resetflag = 0
            print('主控板 solt id={} 查询设备获取主控信息{}'.format(masterSoltId, masterInfo))
            if getrowdata('升级bootrom文件名', rowData) is None and getrowdata('升级Software文件名', rowData) is None \
                    and getrowdata('升级FPGA文件名', rowData) is None and getrowdata('升级CPLD文件名', rowData) is None:
                print('主控版没有填升级文件，不用升级')
                #text.insert('end', '\n {}'.format('升级文件名空,不用升级'))
                pass
            else:
                if backInfo is not None:
                    ##有主控备板 需要ha
                    if backInfo.get('Slot') == masterSoltId:
                        print('已经切换好了')
                        outmsg.outtext('主控板已经切换好了')
                        pass
                    else:
                        print('主控板开始ha切换备板')
                        outmsg.outtext('主控板开始ha切换备板')
                        print(dev_info)
                        net_connect, ha_result = haswitch(masterSoltId, net_connect, **dev_info)


                        if ha_result == False:
                            msgtext = 'ha切换失败请检查 {}'.format(rowData)
                            outmsg.outtext('主ha切换失败请检查')
                            outmsg.finnalRes('连接设备失败')
                            msgqueue.put(outmsg)
                            return rowData
                        else:
                            outmsg.outtext('ha 切换成功')
                    ##做ha 切换
                    ## 表已经切换好了
                    pass
                else:
                    onemaster = True
                    ##只有一张主控板
                    downloadbootrom = ' download    bootrom  ftp '

                if getrowdata('升级bootrom文件名', rowData) is None:
                    print('升级bootrom文件名为空不升级')
                else:
                    print('开始升级 bootrom')
                    outmsg.setupfilename(rowData.get('升级bootrom文件名'))
                    outmsg.outtext('开始升级 ')
                    #text.insert('end', '\n {}  '.format(outmsg.outmsg()))
                    if backInfo is None:
                        ###
                        print('只有单板主控')
                        downloadbootrom = ' download    bootrom  ftp '
                        ftpcmdret = net_connect.send_command(downloadbootrom, expect_string=r':')
                        # slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                        # downret = net_connect.send_command(slotidcmd, expect_string=r':')
                    else:
                        print('有主备主控')
                        downloadbootrom = ' download  svcfile  bootrom  ftp '
                        ftpcmdret = net_connect.send_command(downloadbootrom, expect_string=r':')
                        print(ftpcmdret)
                        slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                        ftpcmdret += net_connect.send_command(slotidcmd, expect_string=r':')

                    ipcmd = '{}'.format(rowData['ftpip'])
                    print(ftpcmdret)
                    ftpcmdret += net_connect.send_command(ipcmd, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret += net_connect.send_command(ftpcmd, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    ftpcmdret = net_connect.send_command(ftpcmd, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData.get('升级bootrom文件名'))
                    print('bootrom file={}'.format(ftpcmd))
                    ftpcmdret = net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = 'y'
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=600, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '{}上传版本成功 '.format(rowData.get('升级bootrom文件名'))
                        print('上传版本成功')
                        outmsg.outtext('上传版本成功')
                        outmsg.bootromRes('上传版本成功')
                        resetFlag = True
                        # resetflag = 1
                        if g_model == "YES":
                            if 2 == 1:
                                pass
                            else:
                                resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                                print('reset cmd={}'.format(resetcmd))
                                resetret = net_connect.send_command(resetcmd)
                                #text.insert('end', '\n {}'.format('开始reset板卡'))
                                outmsg.outtext('{}'.format('开始reset板卡'))
                                time.sleep(10)
                                print('after reset card get slot state')
                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info , net_connectpack)
                                net_connect = net_connectpack[0]
                                print('get resetCard={}'.format(resetCard))
                                resetcount = 0
                                outmsg.outtext('开始等待板卡reset启动')
                                while resetCard.get('State') != 'working' and resetcount < 360:
                                    time.sleep(3)
                                    resetcount = resetcount + 1
                                    net_connectpack = [net_connect]
                                    resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                    net_connect = net_connectpack[0]
                                    print('not card state <> working waiting... 3seconds')
                                print('get working state ={}'.format(resetCard.get('State')))
                                if resetCard.get('State') != 'working':
                                    resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                    print(resulttext)
                                    outmsg.outtext('状态不是working没有起来需要检查')
                                else:
                                    resulttext = '上传版本成功，重启板卡成功'
                                    print('上传版本成功，重启板卡成功')
                                    outmsg.outtext(resulttext)
                                outmsg.outtext('等待板卡ha状态为6',card=True)
                                resetcount = 0
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                time.sleep(10)
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                while hastate != '6' and resetcount < 360:
                                    time.sleep(3)
                                    resetcount = resetcount + 1
                                    hastate = gethastate(outmsg, net_connect, **dev_info)
                                    print('ha state <> 6  now hastate ={}'.format(hastate))
                                resulttext = ' 升级成功重启成功 ' + '板卡HA状态={}'.format(hastate)
                                outmsg.outtext(resulttext)
                        else:
                            outmsg.outtext('上传版本成功,不自动重启')
                    else:
                        resulttext = 'bootrom 上传版本失败'
                        print('上传版本失败')
                        outmsg.outtext(resulttext)



                if getrowdata('升级Software文件名', rowData) is None:
                    print('升级Software文件名为空不升级')
                else:
                    outmsg.setupfilename(rowData.get('升级Software文件名'))
                    print('升级Software {}'.format(rowData.get('升级Software文件名')))
                    #text.insert('end', '\n {}'.format('升级Software {}'.format(rowData.get('升级Software文件名'))))
                    outmsg.outtext('升级Software ')
                    if backInfo is None:
                        ###
                        print('只有单板主控')
                        downloadsystemboot = ' download   system-boot  ftp '

                        ftpcmdret = net_connect.send_command(downloadsystemboot, expect_string=r':')
                    else:
                        print('有主备主控')
                        downloadsystemboot = ' download  svcfile  system-boot  ftp '
                        ftpcmdret = net_connect.send_command(downloadsystemboot,read_timeout=30, expect_string=r':')
                        slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                        ftpcmdret += net_connect.send_command(slotidcmd,read_timeout=30, expect_string=r':')
                    print(downloadsystemboot)
                    print(ftpcmdret)


                    ftpcmd = '{}'.format(rowData['ftpip'])
                    ftpcmdret += net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret += net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    ftpcmdret += net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData.get('升级Software文件名'))
                    ftpcmdret += net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = 'y'
                    print(ftpcmdret)
                    ftpcmdret += net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        outmsg.outtext(resulttext)
                        resetFlag = True
                        #text.insert('end', '\n {} {}'.format(rowData.get('升级Software文件名'), resulttext))
                        if g_model == "YES":
                            if 1 == 2:
                                pass
                                ##一张主控直接reboot
                                rebootcmd = 'reboot'
                                print('reboot ....')
                                rebootret = net_connect.send_command(rebootcmd, expect_string=r'\)')
                                print('reboot return={}'.format(rebootret))
                                time.sleep(2)
                                rebootret = net_connect.send_command('Y', expect_string=r'#')

                                print('rebootret=={}'.format(rebootret))
                                time.sleep(10)
                                net_connect = reconnect(360, 10, dev_info)
                                if net_connect is not None:
                                    alertinfo = '主控板重启成功 '
                                    #text.insert('end', '\n {}'.format(alertinfo))
                                    outmsg.outtext(alertinfo)
                                else:
                                    alertinfo = '主控板重启成功失败请人工检查'
                                    outmsg.outtext(alertinfo)

                            else:
                                resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                                print('reset cmd={}'.format(resetcmd))
                                resetret = net_connect.send_command(resetcmd)
                                time.sleep(10)
                                resulttext = '开始reset板卡'
                                #text.insert('end', '\n {}'.format(resulttext))
                                outmsg.outtext(resulttext)
                                print('after reset card get slot state')
                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                print('get resetCard={}'.format(resetCard))
                                resetcount = 0
                                while resetCard.get('State') != 'working' and resetcount < 360:
                                    time.sleep(3)
                                    resetcount = resetcount + 1
                                    net_connectpack = [net_connect]
                                    resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                    net_connect = net_connectpack[0]
                                    print('not card state <> working waiting... 3seconds')
                                print('get working state ={}'.format(resetCard.get('State')))
                                if resetCard.get('State') != 'working':
                                    resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                    print(resulttext)
                                    outmsg.outtext('状态不是working没有起来需要检查')
                                else:
                                    resulttext = '上传版本成功，重启板卡成功'
                                    print('上传版本成功，重启板卡成功')
                                    outmsg.outtext(resulttext)
                                resetcount = 0
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                time.sleep(10)
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                outmsg.outtext('等待板块卡ha状态为6')
                                while hastate != '6' and resetcount < 360:
                                    time.sleep(3)
                                    resetcount = resetcount + 1
                                    hastate = gethastate(outmsg, net_connect, **dev_info)
                                    print('ha state <> 6  now hastate ={}'.format(hastate))
                                resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                        else:
                            outmsg.outtext('不自动重启')
                    else:
                        resulttext = '上传版本失败'
                        print('上传版本失败')
                    showtext = '升级Software{} {} '.format(rowData.get('升级Software文件名'), resulttext)
                    outmsg.outtext(resulttext)
                if getrowdata('升级FPGA文件名', rowData) is None:
                    print('升级FPGA文件名为空不升级')
                else:
                    print('开始升级 fpga')
                    outmsg.setupfilename(rowData.get('升级FPGA文件名'))
                    #text.insert('end', '\n {} {}'.format('开始升级 fpga',rowData.get('升级FPGA文件名')))
                    if backInfo is None:
                        ###
                        print('只有单板主控')
                        downloadfpga = ' download   fpga  ftp '
                        ftpcmdret = net_connect.send_command(downloadfpga, expect_string=r':')
                    else:
                        print('有主备主控')
                        downloadfpga = ' download  svcfile  fpga  ftp '
                        print(downloadfpga)
                        ftpcmdret = net_connect.send_command(downloadfpga, expect_string=r':')
                        slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])

                        ftpcmdret += net_connect.send_command(slotidcmd, expect_string=r':')

                    ipcmd = '{}'.format(rowData['ftpip'])
                    ftpcmdret = net_connect.send_command(ipcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret = net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    ftpcmdret = net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级FPGA文件名'))
                    net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = 'y'
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        resetFlag = True
                        print('上传版本成功')
                        outmsg.outtext(' 上传版本成功')
                        if g_model == "YES":
                            if 1 == 2:
                                pass
                                ##一张主控直接reboot
                                rebootcmd = 'reboot'
                                print('reboot ....')

                                outmsg.outtext("开始重启板卡请等待", card=True)
                                rebootret = net_connect.send_command(rebootcmd, expect_string=r'\)')
                                print('reboot return={}'.format(rebootret))
                                time.sleep(2)
                                rebootret = net_connect.send_command('Y', expect_string=r'#')

                                print('rebootret=={}'.format(rebootret))
                                time.sleep(10)
                                net_connect = reconnect(360, 10, dev_info)
                                if net_connect is not None:
                                    alertinfo = '板卡重启成功 '
                                    #text.insert('end', '\n {}'.format(alertinfo))
                                    outmsg.outtext(alertinfo)
                                else:
                                    alertinfo = '板卡重启成功失败请人工检查'
                                    outmsg.outtext(alertinfo)

                            else:
                                resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                                print('reset cmd={}'.format(resetcmd))
                                resetret = net_connect.send_command(resetcmd)
                                resulttext = '开始reset板卡'

                                outmsg.outtext("开始重启板卡请等待", card=True)
                                time.sleep(10)
                                print('after reset card get slot state')

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                print('get resetCard={}'.format(resetCard))
                                resetcount = 0
                                while resetCard.get('State') != 'working' and resetcount < 360:
                                    time.sleep(3)
                                    resetcount = resetcount + 1

                                    net_connectpack = [net_connect]
                                    resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                    net_connect = net_connectpack[0]
                                    print('not card state <> working waiting... 3seconds')
                                print('get working state ={}'.format(resetCard.get('State')))
                                if resetCard.get('State') != 'working':
                                    resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                    print(resulttext)
                                else:
                                    resulttext = '上传版本成功，重启板卡成功'
                                    print('上传版本成功，重启板卡成功')

                                resetcount = 0
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                time.sleep(10)
                                outmsg.outtext('等待板卡ha状态为6',card=True)
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                while hastate != '6' and resetcount < 360:
                                    time.sleep(3)
                                    resetcount = resetcount + 1
                                    hastate = gethastate(outmsg, net_connect, **dev_info)
                                    print('ha state <> 6  now hastate ={}'.format(hastate))
                                resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                        else:
                            outmsg.outtext('不自动重启')
                    else:
                        resulttext = '上传版本失败'
                        print('上传版本失败')

                    showtext = '升级FPGA{} {} '.format(rowData.get('升级FPGA文件名'), resulttext)
                    outmsg.outtext(resulttext)

                if getrowdata('升级CPLD文件名', rowData) is None:
                    print('升级CPLD文件名为空不升级')
                else:
                    print('开始升级 cpld')
                    #text.insert('end', '\n {}'.format('开始升级 cpld {}'.format(rowData.get('升级CPLD文件名'))))
                    outmsg.setupfilename(rowData.get('升级CPLD文件名'))
                    outmsg.outtext( '开始升级 ')
                    if backInfo is None:
                        ###
                        print('只有单板主控')
                        downloadcpld = ' download   cpld  ftp '
                        print(downloadcpld)
                        ftpcmdret = net_connect.send_command(downloadcpld, expect_string=r':')
                    else:
                        print('有主备主控')
                        downloadcpld = ' download svcfile  cpld    ftp '
                        print(downloadcpld)
                        ftpcmdret = net_connect.send_command(downloadcpld, expect_string=r':')
                        print(ftpcmdret)
                        slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                        ftpcmdret += net_connect.send_command(slotidcmd, expect_string=r':')
                    print(ftpcmdret)
                    ipcmd = '{}'.format(rowData['ftpip'])
                    ftpcmdret += net_connect.send_command(ipcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret += net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    ftpcmdret += net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级CPLD文件名'))
                    ftpcmdret += net_connect.send_command(ftpcmd, expect_string=r':')
                    needreboot = False
                    ftpcmd = 'y'
                    ftpcmdret += net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        print('上传版本成功')
                        outmsg.outtext(' 上传版本成功')
                        #text.insert('end', '\n {} {}'.format(rowData.get('升级CPLD文件名') , resulttext))
                        if g_model == "YES":
                            if 1 == 2:
                                pass
                                ##一张主控直接reboot
                                rebootcmd = 'reboot'
                                print('reboot ....')
                                outmsg.outtext("开始重启板卡请等待",card=True)
                                rebootret = net_connect.send_command(rebootcmd, expect_string=r'\)')
                                print('reboot return={}'.format(rebootret))
                                time.sleep(2)
                                rebootret = net_connect.send_command('y', expect_string=r'#')

                                print('rebootret=={}'.format(rebootret))
                                time.sleep(10)
                                net_connect = reconnect(360, 10, dev_info)
                                if net_connect is not None:
                                    alertinfo = '主控板重启成功 '
                                    #text.insert('end', '\n {}'.format(alertinfo))
                                    outmsg.outtext(alertinfo)
                                else:
                                    alertinfo = '主控板重启成功失败请人工检查'
                                    #text.insert('end', '\n {}'.format(alertinfo))
                                    outmsg.outtext(alertinfo)
                            else:
                                # resetflag = 1
                                resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                                resetret = net_connect.send_command(resetcmd)
                                time.sleep(10)


                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                resetcount = 0
                                while resetCard.get('State') != 'working' and resetcount < 360:
                                    time.sleep(10)
                                    resetcount = resetcount + 1

                                    net_connectpack = [net_connect]
                                    resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                    net_connect = net_connectpack[0]
                                    print('not card state <> working waiting... 10seconds')
                                print('get working state ={}'.format(resetCard.get('State')))
                                if resetCard.get('State') != 'working':
                                    alertinfo = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                    #text.insert('end', '\n {}'.format(alertinfo))
                                else:
                                    resulttext = '上传版本成功，重启板卡成功'
                                    print('上传版本成功，重启板卡成功')
                        else:
                            outmsg.outtext('不自动重启')
                    else:

                        net_connectpack = [net_connect]
                        resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                        net_connect = net_connectpack[0]
                        resetcount = 0
                        while resetCard.get('State') != 'working' and resetcount < 360:
                            time.sleep(10)
                            resetcount = resetcount + 1

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('not card state <> working waiting... 10seconds')
                        print('get working state ={}'.format(resetCard.get('State')))
                        if resetCard.get('State') != 'working':
                            alertinfo = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                            #text.insert('end', '\n {}'.format(alertinfo))
                        else:
                            resulttext = '升级成功'
                            print(resulttext)

                    showtext = '升级CPLD{} {} '.format(rowData.get('升级CPLD文件名'), resulttext)
                    #text.insert('end', '\n {}'.format(showtext))
                    outmsg.outtext(resulttext)
                '''
                ##一次性重启 reset
                ##reset card
                if needreboot == True:
                    if onemaster:
                        pass
                        ##一张主控直接reboot
                        rebootcmd = 'reboot'
                        print('reboot ....')
                        outmsg.outtext("开始重启板卡请等待",card=True)
                        rebootret = net_connect.send_command(rebootcmd, expect_string=r'\)')
                        print('reboot return={}'.format(rebootret))
                        time.sleep(2)
                        rebootret = net_connect.send_command('y', expect_string=r'#')

                        print('rebootret=={}'.format(rebootret))
                        time.sleep(10)
                        net_connect = reconnect(360, 10, dev_info)
                        if net_connect is not None:
                            alertinfo = '主控板重启成功 '
                            # text.insert('end', '\n {}'.format(alertinfo))
                            outmsg.outtext(alertinfo)
                        else:
                            alertinfo = '主控板重启成功失败请人工检查'
                            # text.insert('end', '\n {}'.format(alertinfo))
                            outmsg.outtext(alertinfo)
                    else:
                        # resetflag = 1
                        outmsg.outtext("开始重启板卡请等待",card=True)
                        resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                        resetret = net_connect.send_command(resetcmd)
                        time.sleep(10)

                        net_connectpack = [net_connect]
                        resetCard = getslotstate(rowData.get('solt id'), dev_info, net_connectpack)
                        net_connect = net_connectpack[0]
                        resetcount = 0
                        while resetCard.get('State') != 'working' and resetcount < 360:
                            time.sleep(10)
                            resetcount = resetcount + 1

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'), dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('not card state <> working waiting... 10seconds')
                        print('get working state ={}'.format(resetCard.get('State')))
                        if resetCard.get('State') != 'working':
                            alertinfo = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                            # text.insert('end', '\n {}'.format(alertinfo))
                        else:
                            resulttext = '上传版本成功，重启板卡成功'
                            print('上传版本成功，重启板卡成功')
                        resetcount = 0
                        hastate = gethastate(outmsg, net_connect, **dev_info)
                        time.sleep(10)
                        outmsg.outtext('等待板卡ha状态为6',card=True)
                        hastate = gethastate(outmsg, net_connect, **dev_info)
                        while hastate != '6' and resetcount < 360:
                            time.sleep(3)
                            resetcount = resetcount + 1
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            print('ha state <> 6  now hastate ={}'.format(hastate))

                        if hastate != '6':
                            outmsg.outtext('板卡HA状态不为6，需要检查')
                        else:
                            outmsg.outtext('板卡HA状态为6，升级成功')
            '''


        if rowData['板卡属性'] == '主控备板':
            print('主控备板 升级开始...')
            resetflag = 0
            outmsg.setupfilename(rowData.get('升级bootrom文件名'))
            print('filename type ={}'.format(type(rowData.get('升级bootrom文件名'))))
            if getrowdata('升级bootrom文件名', rowData) is None and getrowdata('升级Software文件名', rowData) is None \
                    and getrowdata('升级FPGA文件名', rowData) is None and getrowdata('升级CPLD文件名', rowData) is None:
                print('主控备板没有填升级文件，不用升级')
                text.insert('end', '\n {}'.format('升级文件名空,不用升级'))
                pass
            else:
                if masterInfo is not None:
                    ##有主控备板 需要ha
                    if masterInfo.get('Slot') == rowData.get('solt id'):
                        print('备板已经是主控要做ha切换')
                        ###
                        net_connect, ha_result = haswitch(masterInfo.get('Slot'), net_connect, **dev_info)
                        if ha_result == False:
                            msgtext = 'ha切换失败请检查 {}'.format(rowData)
                            #text.insert('end', '\n {}'.format(msgtext))
                            outmsg.finnalRes('ha切换失败请检查')
                            msgqueue.put(outmsg)
                            outmsg.outtext('ha切换失败请检查')
                            return 'ha切换失败请检查'
                        pass
                    else:
                        print('二次确认主控备板是备状态')
                        pass
                    ##做ha 切换
                    ## 表面已经切换好了
                if getrowdata('升级bootrom文件名', rowData) is None:
                    print('升级bootrom文件名为空不升级')
                else:
                    print('开始升级 bootrom')
                    outmsg.setupfilename(rowData.get('升级bootrom文件名'))
                    #text.insert('end', '\n {}'.format('升级bootrom {}'.format(rowData.get('升级bootrom文件名'))))
                    outmsg.outtext('开始升级')
                    cmd = ' download  svcfile  bootrom  ftp '
                    print(cmd)
                    ftpcmdret = net_connect.send_command(cmd, read_timeout=10, expect_string=r':')
                    print(ftpcmdret)
                    slotidcmd = '{} {}'.format('slot', rowData['solt id'])
                    print(slotidcmd)
                    ftpcmdret = net_connect.send_command(slotidcmd, read_timeout=10, expect_string=r':')
                    print(ftpcmdret)
                    ipcmd = '{}'.format(rowData['ftpip'])
                    print(ipcmd)
                    ftpcmdret = net_connect.send_command(rowData['ftpip'], read_timeout=10, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=10, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=10, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData.get('升级bootrom文件名'))
                    print('bootrom file={}'.format(ftpcmd))
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=10, expect_string=r':')
                    ftpcmd = 'y'
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        print('上传版本成功')
                        resetFlag = True

                        outmsg.outtext('上传版本成功')
                        outmsg.bootromRes('上传版本成功')
                        if g_model == "YES":
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            resulttext = 'reset 板卡'
                            #text.insert('end', '\n {}'.format(resulttext))
                            outmsg.outtext('reset板卡 需要等待')
                            print('after reset card get slot state')

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resetcount = 0
                            while resetCard.get('State') != 'working' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                print(resulttext)
                                outmsg.bootromRes(resulttext)
                                outmsg.outtext(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                print('上传版本成功，重启板卡成功')
                                outmsg.bootromRes(resulttext)
                                outmsg.outtext(resulttext)

                            resetcount = 0
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            resulttext = '板卡HA状态={}'.format(hastate)
                        else:
                            outmsg.outtext("不自动重启")
                    else:
                        resulttext = '上传版本失败'
                        outmsg.bootromRes(resulttext)
                        print('上传版本失败')

                    showtext = 'bootrom {} {}'.format(rowData.get('升级bootrom文件名'), resulttext)
                    outmsg.outtext(resulttext)

                if getrowdata('升级Software文件名', rowData) is None:
                    print('升级Software文件名为空不升级')
                else:
                    print('开始升级 software')
                    outmsg.setupfilename(rowData.get('升级Software文件名'))
                    print('software filename ={}'.format(rowData.get('升级Software文件名')))
                    outmsg.outtext('开始升级 ')
                    #text.insert('end', '\n {}'.format('software={}'.format(rowData.get('升级Software文件名'))))
                    downloadbootrom = ' download  svcfile  system-boot   ftp '
                    ftpcmdret = net_connect.send_command(downloadbootrom,read_timeout=30, expect_string=r':')
                    slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    ftpcmdret += net_connect.send_command(slotidcmd,read_timeout=30, expect_string=r':')

                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpip'])
                    print(ftpcmd)
                    print(ftpcmdret)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=30,expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    print(ftpcmd)
                    print(ftpcmdret)
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    print(ftpcmd)
                    print(ftpcmdret)
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData.get('升级Software文件名'))
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = 'y'
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print('get upload system-boot result={}'.format(ftpcmdret))
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        print('上传版本成功')
                        resetFlag = True
                        # resetflag = 1
                        outmsg.outtext('上传版本成功')
                        outmsg.softwareRes(resulttext)
                        if g_model == "YES":
                            #text.insert('end', '\n {} {}'.format(rowData.get('升级Software文件名'), resulttext))
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            print('after reset card get slot state')
                            resulttext = 'reset 板卡'
                            #text.insert('end', '\n {}'.format(resulttext))
                            outmsg.outtext(resulttext)

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resetcount = 0
                            while resetCard.get('State') != 'working' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                print(resulttext)
                                resulttext = '上传版本成功，状态不是working'
                                outmsg.softwareRes(resulttext)

                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                outmsg.softwareRes(resulttext)
                                print('上传版本成功，重启板卡成功')

                            ''' 
                            resetcount = 0
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                            outmsg.softwareRes(resulttext)
                            '''
                        else:
                            outmsg.outtext("不自动重启")
                            resulttext = '上传版本失败'
                            outmsg.softwareRes(resulttext)
                            print('上传版本失败')

                    else:
                        outmsg.outtext("上传版本失败")
                        outmsg.softwareRes("上传版本失败")
                if getrowdata('升级FPGA文件名', rowData) is None:
                    print('升级FPGA文件名为空不升级')
                else:
                    print('开始升级 fpga')
                    outmsg.setupfilename(rowData.get('升级FPGA文件名'))
                    showtext ='开始升级 fpga  {}'.format(rowData.get('升级FPGA文件名'))
                    #text.insert('end', '\n {}'.format('开始升级 fpga  {}'.format(rowData.get('升级FPGA文件名'))))
                    outmsg.outtext('开始升级')
                    downloadbootrom = ' download  svcfile fpga      ftp '
                    downret = net_connect.send_command(downloadbootrom, expect_string=r':')
                    slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    downret = net_connect.send_command(slotidcmd, expect_string=r':')
                    ipcmd = '{}'.format(rowData['ftpip'])
                    ipcmdret = net_connect.send_command(ipcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret = net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    portcmdret = net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级FPGA文件名'))
                    net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = 'y'
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=600, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        print('上传版本成功')
                        resetFlag = True
                        outmsg.fpgaRes(resulttext)
                        if g_model == "YES":
                            #text.insert('end', '\n {} {}'.format(rowData.get('升级FPGA文件名') , resulttext))
                            showtext = '{} 上传版本成功 '.format(rowData.get('升级FPGA文件名'))
                            outmsg.outtext('上传版本成功')
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            print('after reset card get slot state')
                            resulttext = 'reset 板卡'
                            #text.insert('end', '\n {}'.format(resulttext))
                            outmsg.outtext(resulttext)

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resetcount = 0
                            while resetCard.get('State') != 'working' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                print(resulttext)
                                outmsg.fpgaRes(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                outmsg.fpgaRes(resulttext)
                                print('上传版本成功，重启板卡成功')

                            outmsg.outtext(resulttext)
                            resetcount = 0
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            '''
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                            outmsg.fpgaRes(resulttext)
                            '''
                        else:
                            outmsg.outtext("不自动重启")
                    else:
                        resulttext = '上传版本失败'
                        outmsg.fpgaRes(resulttext)
                        print('上传版本失败')
                    showtext = '升级FPGA {} {}'.format(rowData.get('升级FPGA文件名'), resulttext)
                    outmsg.outtext(resulttext)


                if getrowdata('升级CPLD文件名', rowData) is None:
                    print('升级CPLD文件名为空不升级')
                else:
                    pass
                    print('开始升级cpld')
                    outmsg.setupfilename(rowData.get('升级CPLD文件名'))
                    showtext = '开始升级cpld ={}'.format(rowData.get('升级CPLD文件名'))
                    outmsg.outtext('开始升级')
                    #text.insert('end', '\n {}'.format('开始升级cpld ={}'.format(rowData.get('升级CPLD文件名'))))
                    downloadbootrom = ' download  svcfile cpld      ftp '
                    downret = net_connect.send_command(downloadbootrom,read_timeout=30, expect_string=r':')
                    slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    downret = net_connect.send_command(slotidcmd, read_timeout=30,expect_string=r':')
                    ipcmd = '{}'.format(rowData['ftpip'])
                    ipcmdret = net_connect.send_command(ipcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    portcmdret = net_connect.send_command(ftpcmd, read_timeout=30,expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级CPLD文件名'))
                    net_connect.send_command(ftpcmd, read_timeout=100, expect_string=r':')
                    ftpcmd = 'y'
                    needreboot = False
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        print('上传版本成功')
                        # resetflag = 1
                        outmsg.outtext('上传版本成功')
                        outmsg.fpgaRes(resulttext)
                        if g_model == "YES":
                            #text.insert('end', '\n {} {}'.format(rowData.get('升级CPLD文件名'), resulttext))
                            outmsg.outtext('reset等待')
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(3)

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            resetcount = 0
                            while resetCard.get('State') != 'working' and resetcount < 360:
                                time.sleep(10)
                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                print('not card state <> working waiting... 10seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                alertinfo = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                #text.insert('end', '\n {}'.format(alertinfo))
                                outmsg.fpgaRes(alertinfo)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                outmsg.outtext(resulttext)
                                print('上传版本成功，重启板卡成功')
                                outmsg.outtext('板卡reset成功，等待ha 状态变成6')
                                print('板卡reset成功，等待ha 状态变成6')
                                #text.insert('end', '\n {}'.format('板卡reset成功，等待ha 状态变成6'))
                                time.sleep(10)
                                ''' 
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                while hastate != '6' and resetcount < 360:
                                    time.sleep(3)
                                    msgtemp = 'HA 状态不是6 继续等待'

                                    resetcount = resetcount + 1
                                    hastate = gethastate(outmsg, net_connect, **dev_info)
                                    print('ha state <> 6  now hastate ={}'.format(hastate))
                                if hastate != '6':
                                    print('ha state <> 6  now hastate ={}'.format(hastate))
                                    resulttext = '上传版本成功，重启板卡成功 ha状态不为6需要检查'
                                    outmsg.fpgaRes(resulttext)
                                    # text.insert('end', '\n {}'.format('板卡reset成功， ha状态不是6 请检查'))
                                else:
                                    print('上传版本成功，重启板卡成功 ha状态切换成6')
                                    resulttext = '上传版本成功，重启板卡成功 ha状态切换成6'
                                    outmsg.fpgaRes(resulttext)
                                    #text.insert('end', '\n {}'.format('板卡reset成功， ha状态切换成6'))
                                    '''
                        else:
                            outmsg.outtext("不自动重启")
                    else:
                        resulttext = '上传版本失败'
                        outmsg.fpgaRes(resulttext)
                        print('上传版本失败')
                    showtext = '升级CPLD文件名 {} {}'.format(rowData.get('升级CPLD文件名'), resulttext)
                    outmsg.outtext(resulttext)
                '''
                if needreboot == True:
                    if onemaster:
                        pass
                        ##一张主控直接reboot
                        rebootcmd = 'reboot'
                        print('reboot ....')
                        outmsg.outtext("开始重启板卡请等待",card=True)
                        rebootret = net_connect.send_command(rebootcmd, expect_string=r'\)')
                        print('reboot return={}'.format(rebootret))
                        time.sleep(2)
                        rebootret = net_connect.send_command('y', expect_string=r'#')

                        print('rebootret=={}'.format(rebootret))
                        time.sleep(10)
                        net_connect = reconnect(360, 10, dev_info)
                        if net_connect is not None:
                            alertinfo = '主控板重启成功 '
                            # text.insert('end', '\n {}'.format(alertinfo))
                            outmsg.outtext(alertinfo)
                        else:
                            alertinfo = '主控板重启成功失败请人工检查'
                            # text.insert('end', '\n {}'.format(alertinfo))
                            outmsg.outtext(alertinfo)
                    else:
                        # resetflag = 1
                        outmsg.outtext("开始重启板卡请等待",card=True)
                        resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                        resetret = net_connect.send_command(resetcmd)
                        time.sleep(10)

                        net_connectpack = [net_connect]
                        resetCard = getslotstate(rowData.get('solt id'), dev_info, net_connectpack)
                        net_connect = net_connectpack[0]
                        resetcount = 0
                        while resetCard.get('State') != 'working' and resetcount < 360:
                            time.sleep(10)
                            resetcount = resetcount + 1

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'), dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('not card state <> working waiting... 10seconds')
                        print('get working state ={}'.format(resetCard.get('State')))
                        if resetCard.get('State') != 'working':
                            alertinfo = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                            # text.insert('end', '\n {}'.format(alertinfo))
                        else:
                            resulttext = '上传版本成功，重启板卡成功'
                            print('上传版本成功，重启板卡成功')
                        resetcount = 0
                        hastate = gethastate(outmsg, net_connect, **dev_info)
                        time.sleep(10)
                        outmsg.outtext('等待板卡ha状态为6',card=True)
                        hastate = gethastate(outmsg, net_connect, **dev_info)
                        while hastate != '6' and resetcount < 360:
                            time.sleep(3)
                            resetcount = resetcount + 1
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            print('ha state <> 6  now hastate ={}'.format(hastate))

                        if hastate != '6':
                            outmsg.outtext('板卡HA状态不为6，需要检查')
                        else:
                            outmsg.outtext('板卡HA状态为6，升级成功')
                '''
        if rowData['板卡属性'] == '业务板':

            print('业务板 升级开始...')
            print('{}'.format(rowData))
            if getrowdata('升级bootrom文件名', rowData) is None and getrowdata('升级Software文件名', rowData) is None \
                    and getrowdata('升级FPGA文件名', rowData) is None and getrowdata('升级CPLD文件名', rowData) is None:
                print('升级文件名空,不用升级')
                #text.insert('end', '\n {}'.format('升级文件名空,不用升级'))
                pass

            else:
                if getrowdata('升级bootrom文件名', rowData) is None:
                    print('升级bootrom文件名为空不升级')
                else:
                    print('开始升级BOOTROM...')
                    showtext = '升级bootrom  {}'.format(rowData.get('升级bootrom文件名'))
                    outmsg.setupfilename(rowData.get('升级bootrom文件名'))
                    outmsg.outtext('开始升级')
                    #text.insert('end', '\n {}'.format(showtext))
                    downloadbootrom = ' download  svcfile  bootrom  ftp '
                    downret = net_connect.send_command(downloadbootrom,read_timeout=30, expect_string=r':')
                    slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    downret = net_connect.send_command(slotidcmd,read_timeout=30, expect_string=r':')
                    ipcmd = '{}'.format(rowData['ftpip'])
                    ipcmdret = net_connect.send_command(ipcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    portcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级bootrom文件名'))
                    net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = 'y'
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        resetFlag = True
                        print('上传版本成功')
                        outmsg.outtext(' 上传版本成功 ')
                        outmsg.bootromRes('上传版本成功')

                        if g_model == "YES":
                            #text.insert('end', '\n {} {} '.format(rowData.get('升级bootrom文件名') , resulttext))
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            print('after reset card get slot state')
                            resulttext = 'reset 板卡'
                            outmsg.outtext(resulttext)
                            #text.insert('end', '\n {}'.format(resulttext))

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resetcount = 0
                            NewCardState = 'wrong' if resetCard is None else resetCard.get('State')


                            while NewCardState != 'working' and resetcount < 360:
                                time.sleep(3)

                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') == 'working':
                                resulttext = '上传版本成功，重启板卡成功'
                                print('上传版本成功，重启板卡成功')
                                outmsg.bootromRes(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡状态不是working'
                                print('上传版本成功，重启板卡状态不是working')
                                outmsg.bootromRes(resulttext)

                            resetcount = 0
                            ##业务办卡是不是不要等ha 状态 先屏蔽
                            '''
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            if hastate != '6':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                outmsg.bootromRes(resulttext)
                                print(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                print('上传版本成功，重启板卡成功')
                                outmsg.bootromRes(resulttext)
                            
                            resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                            '''
                            #text.insert('end', '\n {}'.format(resulttext))
                        else:
                            outmsg.outtext("不自动重启")
                    else:

                        resulttext = '升级失败'
                        outmsg.bootromRes(resulttext)
                        #text.insert('end', '\n {}'.format(resulttext))
                        print('升级失败')
                    outmsg.outtext(resulttext)
                if getrowdata('升级Software文件名', rowData) is None:
                    print('升级Software文件名为空不升级')
                else:
                    time.sleep(5)
                    resulttext = '开始升级业务板卡software {}'.format(rowData.get('升级Software文件名') )
                    print('开始升级业务板卡software...')
                    outmsg.setupfilename(rowData.get('升级Software文件名'))
                    #text.insert('end', '\n {} {}'.format(resulttext ,rowData.get('升级Software文件名') ))
                    outmsg.outtext('开始升级')
                    ftpcmd = ' download   svcfile  system-boot    ftp '
                    if "PG8" in rowData['PowerName'] or "PX4" in rowData['PowerName']:
                        ftpcmd = ' download    svcfile mcu ftp      '
                    #text.insert('end', '\n 开始升级software '.format(rowData.get('升级Software文件名')))
                    print('业务板卡升级命令={}'.format(ftpcmd))
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=30,expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpip'])
                    print(ftpcmd)
                    print(ftpcmdret)
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    print(ftpcmd)
                    print(ftpcmdret)
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    print(ftpcmd)
                    print(ftpcmdret)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=30,expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = '{}'.format(rowData.get('升级Software文件名'))
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    print(ftpcmdret)
                    ftpcmd = 'y'
                    print(ftpcmd)
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        resulttext = '上传版本成功'
                        resetFlag = True
                        print('上传版本成功')
                        outmsg.outtext('上传版本成功')
                        outmsg.softwareRes('上传版本成功')
                        if g_model == "YES":
                            #text.insert('end', '\n {} {}'.format(rowData.get('升级Software文件名'), resulttext))
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            print('after reset card get slot state')

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resetcount = 0
                            resulttext = 'reset 板卡'
                            #text.insert('end', '\n {}'.format(resulttext))
                            outmsg.outtext(resulttext)
                            NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')

                            while NewCardState != 'working' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                print(resulttext)
                                outmsg.softwareRes(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                outmsg.softwareRes(resulttext)
                                print('上传版本成功，重启板卡成功')
                            outmsg.outtext(resulttext)
                            resetcount = 0
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            '''
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                            #text.insert('end', '\n {}'.format(resulttext))
                            outmsg.outtext(resulttext)
                            '''
                        else:
                            outmsg.outtext("不自动重启")
                    else:
                        resulttext = '升级失败'
                        print('升级失败')
                        outmsg.softwareRes(resulttext)
                    showtext = '升级Software {} {}'.format(rowData.get('升级Software文件名'), resulttext)
                    outmsg.outtext(resulttext)
                if getrowdata('升级FPGA文件名', rowData) is None:
                    print('升级FPGA文件名为空不升级')
                else:
                    print('开始升级FPGA...')
                    resulttext = '开始升级FPGA...'
                    outmsg.outtext('开始升级 ')
                    outmsg.setupfilename(rowData.get('升级FPGA文件名'))
                    #text.insert('end', '\n {} {} '.format(resulttext,rowData.get('升级FPGA文件名')))
                    downloadbootrom = ' download  svcfile fpga      ftp '
                    print(downloadbootrom)
                    downret = net_connect.send_command(downloadbootrom,read_timeout=30, expect_string=r':')
                    slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    downret = net_connect.send_command(slotidcmd,read_timeout=30, expect_string=r':')
                    ipcmd = '{}'.format(rowData['ftpip'])
                    ipcmdret = net_connect.send_command(ipcmd, read_timeout=30,expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    portcmdret = net_connect.send_command(ftpcmd, read_timeout=30,expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级FPGA文件名'))
                    net_connect.send_command(ftpcmd, expect_string=r':')
                    ftpcmd = 'y'
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)

                    if 'Copy file successfully!' in ftpcmdret:
                        print('上传文件成功')
                        resetFlag = True
                        resulttext = '上传文件成功'
                        outmsg.outtext('上传文件成功')
                        outmsg.softwareRes(resulttext)
                        if g_model == "YES":
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            print('after reset card get slot state')
                            resulttext = 'reset 板卡'
                            outmsg.outtext(resulttext)
                            #text.insert('end', '\n {}'.format(resulttext))

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resetcount = 0
                            NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')

                            while NewCardState != 'working' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1

                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                print(resulttext)
                                outmsg.softwareRes(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                outmsg.softwareRes(resulttext)
                                print('上传版本成功，重启板卡成功')
                            outmsg.outtext(resulttext)
                            resetcount = 0
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                        else:
                            outmsg.outtext("不自动重启")
                    else:
                        resulttext = '{}上传版本失败'.format(rowData.get('升级FPGA文件名'))
                        outmsg.softwareRes(resulttext)
                        print('上传版本失败')
                    outmsg.outtext(resulttext)
                    #text.insert('end', '\n {}'.format(resulttext))


                if getrowdata('升级CPLD文件名', rowData) is None:
                    print('升级CPLD文件名为空不升级')
                else:
                    print('升级CPLD...')
                    resulttext = '升级CPLD...'
                    outmsg.setupfilename(rowData.get('升级CPLD文件名'))
                    outmsg.outtext('开始升级')
                    downloadbootrom = ' download  svcfile cpld      ftp '
                    downret = net_connect.send_command(downloadbootrom,read_timeout=30, expect_string=r':')
                    slotidcmd = '{} {}'.format(' slot ', rowData['solt id'])
                    downret = net_connect.send_command(slotidcmd,read_timeout=30, expect_string=r':')
                    ipcmd = '{}'.format(rowData['ftpip'])
                    ipcmdret = net_connect.send_command(ipcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftpuser'])
                    ftpcmdret = net_connect.send_command(ftpcmd,read_timeout=30, expect_string=r':')
                    ftpcmd = '{}'.format(rowData['ftppasswd'])
                    portcmdret = net_connect.send_command(ftpcmd, read_timeout=30,expect_string=r':')
                    ftpcmd = '{}'.format(rowData.get('升级CPLD文件名'))
                    net_connect.send_command(ftpcmd, read_timeout=2000, expect_string=r':')
                    ftpcmd = 'y'
                    needreboot = False
                    ftpcmdret = net_connect.send_command(ftpcmd, read_timeout=1000, expect_string=r'#')
                    print(ftpcmdret)
                    if 'Copy file successfully!' in ftpcmdret:
                        print('升级成功')
                        resetFlag = True
                        resulttext = '上传文件成功'
                        outmsg.cpldRes(resulttext)
                        if  g_model == "YES":
                            #text.insert('end', '\n {} {} '.format(rowData.get('升级CPLD文件名'), resulttext))
                            outmsg.outtext(' 升级成功')
                            resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                            print('reset cmd={}'.format(resetcmd))
                            resetret = net_connect.send_command(resetcmd)
                            time.sleep(10)
                            print('after reset card get slot state')

                            net_connectpack = [net_connect]
                            resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                            net_connect = net_connectpack[0]
                            print('get resetCard={}'.format(resetCard))
                            resulttext = 'reset 板卡'
                            outmsg.outtext(resulttext)
                            #text.insert('end', '\n {}'.format(resulttext))
                            resetcount = 0
                            NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')
                            while NewCardState != 'working' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                net_connectpack = [net_connect]
                                resetCard = getslotstate(rowData.get('solt id'),  dev_info, net_connectpack)
                                net_connect = net_connectpack[0]
                                NewCardState = 'wrong' if  resetCard is None  else   resetCard.get('State')
                                print('not card state <> working waiting... 3seconds')
                            print('get working state ={}'.format(resetCard.get('State')))
                            if resetCard.get('State') != 'working':
                                resulttext = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                                print(resulttext)
                                outmsg.cpldRes(resulttext)
                            else:
                                resulttext = '上传版本成功，重启板卡成功'
                                outmsg.cpldRes(resulttext)
                                print('上传版本成功，重启板卡成功')
                            outmsg.outtext(resulttext)

                            resetcount = 0
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            time.sleep(10)
                            outmsg.outtext('等待板卡ha状态为6')
                            hastate = gethastate(outmsg, net_connect, **dev_info)
                            while hastate != '6' and resetcount < 360:
                                time.sleep(3)
                                resetcount = resetcount + 1
                                hastate = gethastate(outmsg, net_connect, **dev_info)
                                print('ha state <> 6  now hastate ={}'.format(hastate))
                            resulttext = resulttext + '板卡HA状态={}'.format(hastate)
                        else:
                            outmsg.outtext("不自动重启")
                    else:
                        resulttext = '{}上传版本失败'.format(rowData.get('升级FPGA文件名'))
                        print('升级失败')
                        outmsg.cpldRes(resulttext)
                    outmsg.outtext(resulttext)
                ###要修改 是否需要删除
                '''
                if needreboot == True and  g_model == "YES":

                    # resetflag = 1
                    outmsg.outtext("开始重启板卡请等待",card=True)
                    resetcmd = 'reset card {}'.format(rowData.get('solt id'))
                    resetret = net_connect.send_command(resetcmd)
                    time.sleep(10)

                    net_connectpack = [net_connect]
                    resetCard = getslotstate(rowData.get('solt id'), dev_info, net_connectpack)
                    net_connect = net_connectpack[0]
                    resetcount = 0
                    while resetCard.get('State') != 'working' and resetcount < 360:
                        time.sleep(10)
                        resetcount = resetcount + 1

                        net_connectpack = [net_connect]
                        resetCard = getslotstate(rowData.get('solt id'), dev_info, net_connectpack)
                        net_connect = net_connectpack[0]
                        print('not card state <> working waiting... 10seconds')
                    print('get working state ={}'.format(resetCard.get('State')))
                    if resetCard.get('State') != 'working':
                        alertinfo = '板卡{} 状态不是working没有起来需要检查'.format(rowData.get('solt id'))
                        # text.insert('end', '\n {}'.format(alertinfo))
                    else:
                        resulttext = '上传版本成功，重启板卡成功'
                        print('上传版本成功，重启板卡成功')
                    resetcount = 0
                    hastate = gethastate(outmsg, net_connect, **dev_info)
                    time.sleep(10)
                    outmsg.outtext('等待板卡ha状态为6')
                    hastate = gethastate(outmsg, net_connect, **dev_info)
                    while hastate != '6' and resetcount < 360:
                        time.sleep(3)
                        resetcount = resetcount + 1
                        hastate = gethastate(outmsg, net_connect, **dev_info)
                        print('ha state <> 6  now hastate ={}'.format(hastate))

                    if hastate != '6':
                        outmsg.outtext('板卡HA状态不为6，需要检查')
                    else:
                        outmsg.outtext('板卡HA状态为6，升级成功')
                '''
        print('dev_info={}'.format(dev_info))
    except netmiko.NetMikoTimeoutException as e:
        print("time out exception")
        #text.insert('end', '\n 连接超时 {}'.format(e))
        #msgqueue.put("timeout异常{}".format(e))

        outmsg.outtext('连接超时')
        print(e)
    except netmiko.ConnectionException as e:
        #msgqueue.put("连接异常{}".format(e))

        outmsg.outtext("连接异常{}".format(e))
    except Exception as e:
        print("unknow  exception")
        #msgqueue.put("未知异常{}".format(e))

        outmsg.outtext("异常{}".format(e))
        #text.insert('end', '\n 处理异常{}'.format(e))

        print(e)

    print('连接到网元')
    msgqueue.put(outmsg)
    return outmsg.resultText


def get_desk_p():
    # 获取桌面路径
    return os.path.join(os.path.expanduser('~'), "Desktop")


desk_oath = get_desk_p()
# print(desk_oath)

now = datetime.datetime.now()

iplist = []
g_running = False
gimportcsvfilename = None
g_total = 0
g_runfinished=0
g_threadnum = 1
threadnumlist = [1,2,4,6,8,10,12,14,16,18]
g_model = ""
def importfile():
    global iplist
    global gimportcsvfilename, g_total
    importcsvfilename = tkinter.filedialog.askopenfilename(title='请选择一个文件', filetypes=[('Excel', '.xls'), \
                                                                                              ])
    gimportcsvfilename = importcsvfilename

    if importcsvfilename is None or importcsvfilename == '':
        return


    file_encoding = get_encoding(importcsvfilename)
    print('{}文件格式={}'.format(gimportcsvfilename, file_encoding))
    iplist = []
    g_total = 0
    '''
    with open(importcsvfilename, encoding=file_encoding) as f:
        f_csv = csv.reader(f)
        header = 0
        for row in f_csv:
            if header == 0:
                header = header + 1
                continue
            print('row12 ={}'.format(row[12]))
            # nei username passwd port
            if len(row[16]) == 0 and len(row[15]) == 0  and len(row[14]) == 0  and len(row[13]) == 0 :
                pass
                print('升级文件字段空此行不升级')
            else:
                iplist.append(row)
                g_total = g_total + 1
                
    '''

    workbook = xlrd.open_workbook(importcsvfilename)
    sheet1 = workbook.sheet_by_index(0)
    ftpsheet = workbook.sheet_by_name('ftp服务器信息')
    ftpip = str(ftpsheet[1,0].value)
    ftpuser=  str(ftpsheet[1,1].value)
    ftppasswd= str(ftpsheet[1,2].value)
    ftpport = str(ftpsheet[1,3].value)
    for ir in range(1, sheet1.nrows):
        rowdata = sheet1.row_values(ir)
        row = [str(int(item)) if isinstance(item , float) else item for item in rowdata]
        row = [str(item).lstrip() for item in rowdata]
        print(row)
        if len(row[16]) == 0 and len(row[15]) == 0 and len(row[14]) == 0 and len(row[13]) == 0:
            pass
            print('升级文件字段空此行不升级')
        else:
            row.append(ftpip)
            row.append(ftpuser)
            row.append(ftppasswd)
            row.append(ftpport)
            print("import row={}".format(row))
            iplist.append(row)
            g_total = g_total + 1

    print("iplist row={}".format(iplist))

    tkinter.messagebox.showinfo(title="提示", message="升级记录数{}".format(g_total))
    qmsg = "升级记录数{}".format(g_total)
    #msgqueue.put(qmsg)
 


def error_callback(error):
    logging.debug(f"Error info: {error}")
    print(f"Error info: {error}")


g_finish = 0


# --noconsole
def call_back(info):
    filename = 'runresult.csv'
    g_finish = g_finish + 1
    print('call_back  info={}'.format(info))
    print('g_finish ={}'.format(g_finish))
    logging.debug('result={}'.format(info))
    print('callback={}'.format(info))
    with open(filename, 'a', newline='') as wf:
        f_wcsv = csv.writer(wf)
        f_wcsv.writerows(info)


def precheckne(svcfilename):
    print('precheck svcfilename={}'.format(gimportcsvfilename))

    pool = multiprocessing.Pool(2)

    k = 0
    for i in iplist:
        k = k + 1

        print(f"开始执行第{i}个任务...")
        logging.debug(f"开始执行第{i}个任务...")
        pool.apply_async(task, args=(i,), callback=call_back, error_callback=error_callback)
    pool.close()
    # pool.join()


rowkey = ['网元ip', '用户名', '密码', '端口号', 'solt id', 'PowerName', '板卡属性', '硬件版本','板卡状态', 'bootrom版本',
          'Software版本',
          'FPGA版本', \
          'CPLD版本', \
          '升级bootrom文件名', '升级Software文件名', '升级FPGA文件名', '升级CPLD文件名' \
    , 'ftpip', 'ftpuser', 'ftppasswd', 'ftpport']


def thread_it( func, args):
    print('in thread it')
    myThread = threading.Thread(target=func, args=args)
    myThread.setDaemon(True)  # 主线程退出就直接让子线程跟随退出,不论是否运行完成。
    myThread.start()

def queueworker(devqueue):
    while  not devqueue.empty():
        devinfo = devqueue.get()
        worker(devinfo)


def worker(iplist):
    #global  g_running
    print('in woker thread......param={}'.format(iplist))
    for inode in iplist:
        print('start task')
        irowDict = dict(zip(rowkey, inode))
        retTxt = task(irowDict)
        #irowDict["升级结果"] = retTxt
        print("dev = {} 升级结果= {} ".format(irowDict,retTxt))
        #msgqueue.put(irowDict)
        #print(irowDict['bootrom版本'])
    deviceip = iplist[0][0]
    text.insert('end', '\n {} 设备:{}升级完成'.format(str(datetime.datetime.now()), deviceip))
    #g_running = False
    #text.insert('end', '\n 任务运行结束')


def subThread(iplist):
    print(iplist)


def startupgrade():
    pass
    global iplist, g_running, rowkey,g_model,runResultfile

    if len(iplist) == 0:
        tkinter.messagebox.showinfo(title="提示", message="请先选择需要升级的csv文件")
        return
    if g_running:
        tkinter.messagebox.showinfo(title="提示", message="升级已经启动不需要点击")
        return
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    runResultfile = "result{}.csv".format(timestamp)
    with open(runResultfile, 'a', newline='') as wf:
        f_wcsv = csv.writer(wf)
        resultHeadLine = [ ["网元ip" ,"solt id","PowerName","板卡属性","硬件版本","板卡状态" , \
             "升级bootrom文件名","升级Software文件名","升级FPGA文件名","升级CPLD文件名", \
              "bootrom升级结果",    "Software升级结果",    "FPGA升级结果",    "CPLD升级结果"]]
        f_wcsv.writerows(resultHeadLine)



    netSet = set()
    g_running = True
    #text.insert('end', '\n---点击升级-----')
    deviceIpinfo = {}
    for inode in iplist:
        ip = inode[0]
        netSet.add(ip)
        deviceInfo = deviceIpinfo.get(ip)

        if deviceInfo == None:
            deviceIpinfo[ip] = [inode]
        else:
            deviceIpinfo[ip].append(inode)
        # text.insert('end', '\n{}'.format(inode))

    print('设备个数={}'.format(len(netSet)))
    threadnum =   threadnumlist[comboxlist.current()]
    modellist = ["NO","YES"]
    g_model = modellist[modelcomboxlist.current()]
    print("选择模式是{}".format(g_model))
    print("选择的线程数{}".format(threadnum))
    run_labelvalue.set("开始运行")
    g_runfinished = 0
    import_button.configure(state="disabled")
    for k,v in deviceIpinfo.items():
        print("kkk={} vvv={}".format(k,v))
        devqueue.put(v)
    for i in range(threadnum):
        thread_it(queueworker,(devqueue,))
    ''' 
    ##多线程池方式gui卡顿
    workparamlist = []
    for k,v in deviceIpinfo.items():
        print("kkk={} vvv={}".format(k,v))
        workparamlist.append((worker , v))
    print(workparamlist)

    with ThreadPoolExecutor(max_workers=2) as pool:
        # 使用线程执行map计算
        # 后面元组有3个元素，因此程序启动3条线程来执行action函数
        print(tuple(workparamlist))
        futures = [pool.submit(func, args) for func, args in workparamlist]
    '''
        #for future in futures:
        #    print(future.result())

    ##多线程方式###
    ##g_running = False
    #thread_it( worker,iplist)

    ''' 
    for inode in iplist:
        print('start task')
        irowDict = dict(zip(rowkey, inode))
        task(irowDict)
        print(irowDict['bootrom版本'])
    '''


def gethastate(slotid,net_connect, **dev_info):
    try:
        hastate = None
        print('gethastate 222')
        net_connect.config_mode('config')
        command = 'show ha state'
        hastatetext = net_connect.send_command(command, read_timeout=5, expect_string='#')
        with open('template/ha.template') as template:
            fsm = textfsm.TextFSM(template)
            try:
                tmp = fsm.ParseText(hastatetext)
                result = tmp
                hastate = result[0][0]
                print('get ha ={}'.format(hastate))
            finally:
                pass

        net_connect.send_command('end', expect_string='#')
    except Exception  as e:
        pass
        print('gethastate 333')
        print('gethastate 连接中断...等待重连')
        net_connect = reconnect(200, 2, dev_info)
        print("33 back")
        try:
            net_connect.config_mode('config')
            command = 'show ha state'
            hastatetext = net_connect.send_command(command, read_timeout=5, expect_string='#')
            with open('template/ha.template') as template:
                fsm = textfsm.TextFSM(template)
                try:
                    tmp = fsm.ParseText(hastatetext)
                    result = tmp
                    hastate = result[0][0]
                    print('get ha ={}'.format(hastate))
                finally:
                    pass
            net_connect.send_command('end', expect_string='#')
        finally:
            print('reconnect fail')
            pass
    except netmiko.exceptions.ReadTimeout:
        print('gethastate 444')
        print('gethastate 连接中断...等待重连')
        net_connect = reconnect(240, 2, dev_info)
        print("44 back")
        try:
            net_connect.config_mode('config')
            command = 'show ha state'
            hastatetext = net_connect.send_command(command, read_timeout=5, expect_string='#')
            with open('template/ha.template') as template:
                fsm = textfsm.TextFSM(template)
                try:
                    tmp = fsm.ParseText(hastatetext)
                    result = tmp
                    hastate = result[0][0]
                    print('get ha ={}'.format(hastate))
                finally:
                    pass
            net_connect.send_command('end', expect_string='#')
        finally:
            print('reconnect fail')
            pass
    except netmiko.exceptions.ConnectionException:
        print('gethastate 555')
        print('gethastate 连接中断...等待重连')
        try:
            net_connect = reconnect(240, 2, dev_info)
            print("555 back")
            net_connect.config_mode('config')
            command = 'show ha state'
            hastatetext = net_connect.send_command(command, read_timeout=5, expect_string='#')
            with open('template/ha.template') as template:
                fsm = textfsm.TextFSM(template)
                try:
                    tmp = fsm.ParseText(hastatetext)
                    result = tmp
                    hastate = result[0][0]
                    print('get ha ={}'.format(hastate))
                finally:
                    pass
            net_connect.send_command('end', expect_string='#')
        finally:
            print('reconnect fail')
            pass
    return hastate
def haswitch(masterSoltId, net_connect, **dev_info):
    command = ' ha manual-switch '
    print('haswitch masterSoltId=',masterSoltId)
    #text.insert('end', '\n ------------hastate----------------\n{}'.format('开始ha切换'))
    try:
        print('haswitch 222')
        net_connect.config_mode('config')
        hastate = net_connect.send_command(command, read_timeout=5, expect_string='#')
        #text.insert('end', '\n ------------hastate----------------\n{}'.format(hastate))
        command = 'show ha state'
        hastate = net_connect.send_command(command, read_timeout=5, expect_string='#')
        #text.insert('end', '\n ------------hastate----------------\n{}'.format(hastate))
        net_connect.send_command('end', expect_string='#')
    except netmiko.exceptions.ReadTimeout:
        print('haswitch 333')
        print('ha已经切换网络连接中断...等待重连')
        time.sleep(10)
        #text.insert('end', '\n ha已经切换网络连接中断 \n{}'.format(dev_info))
        net_connect = ConnectHandler(**dev_info)
        net_connect.enable()

        command = 'show card'
        showcard = net_connect.send_command(command, read_timeout=5, expect_string='#')
        #text.insert('end', '\n ------------showcard----------------\n{}'.format(showcard))
        print('ha切换后板卡{}'.format(showcard))
        with open('template/showcard.template') as template:
            fsm = textfsm.TextFSM(template)
            result = fsm.ParseText(showcard)
            print(result)
            print("get masterino backinfo")
            masterInfo = getMasterNode(result)
            backInfo = getBackNode(result)
        print('backinfo ')
        print(backInfo)
        print('masterSoltId=',masterSoltId)
        if backInfo.get('Slot').strip() == masterSoltId:
            return net_connect, True
        else:
            return net_connect, False

def getslotstatenorecon(slotid,net_connect):
    command = "show card"
    try:
        cardinfo = net_connect.send_command(command)
        with open('template/showcard.template') as template:
            fsm = textfsm.TextFSM(template)
            result = fsm.ParseText(cardinfo)
            print('result')
            resetCard = getIndexNode(result, slotid)
            print('resetCard=={}'.format(resetCard))
            return resetCard
    except  Exception as e:
        return None

def getslotstate(slotid, dev_info,*net_connectinfo):
    command = "show card"
    net_connect = net_connectinfo[0][0]
    try:
        cardinfo = net_connect.send_command(command)

    except  Exception as e:

        print('等待重连。。。')
        #net_connect = ConnectHandler(**dev_info)
        net_connect =reconnect(100,3,dev_info)
        cardinfo = net_connect.send_command(command)
        net_connectinfo[0][0] = net_connect
    except netmiko.exceptions.NetMikoTimeoutException:
        print('NetMikoTimeoutException ')
        print('等待重连。。。')
        #net_connect = ConnectHandler(**dev_info)
        net_connect = reconnect(100, 3, dev_info)
        cardinfo = net_connect.send_command(command)
    except netmiko.exceptions.ConnectionException:
        print('NetMikoTimeoutException ')
        print('等待重连。。。')
        #net_connect = ConnectHandler(**dev_info)
        net_connect = reconnect(100, 3, dev_info)
        cardinfo = net_connect.send_command(command)
    print('cardinfo=={}'.format(cardinfo))

    with open('template/showcard.template') as template:
        fsm = textfsm.TextFSM(template)
        result = fsm.ParseText(cardinfo)
        print('result ={}'.format(result))
        resetCard = getIndexNode(result, slotid)
        print('resetCard=={}'.format(resetCard))
        return resetCard


def reconnect(repeattimes, waittime, dev_info):
    i = 0

    while i < repeattimes:
        try:
            i = i + 1
            print('重连第{}次'.format(i))
            net_connect = ConnectHandler(**dev_info)

            print('net_connect={}'.format(net_connect))
            if net_connect is not None:
                return net_connect

        except  Exception as e:

            print('等待重连。。。')
        except netmiko.exceptions.NetMikoTimeoutException:
            print('NetMikoTimeoutException ')
            print('等待重连。。。')
        except netmiko.exceptions.ConnectionException:
            print('NetMikoTimeoutException ')
            print('等待重连。。。')
    return None




def helpthread(win,text,q):
    global  g_running ,g_runfinished
    #print('in helpthread')
    global gimportcsvfilename,runResultfile
    #msgqueue

    if g_running == True:
        with open(runResultfile, 'a', newline='') as wf:
            while not q.empty():
                content = q.get()
                f_wcsv = csv.writer(wf)
                retlist=[[content.cardinfo["网元ip"],content.cardinfo["solt id"],content.cardinfo["PowerName"],\
                          content.cardinfo["板卡属性"],content.cardinfo["硬件版本"],\
                         content.cardinfo["板卡状态"],content.cardinfo["升级bootrom文件名"],content.cardinfo["升级Software文件名"],\
                         content.cardinfo["升级FPGA文件名"],content.cardinfo["升级CPLD文件名"],\
                          content.cardbootromRes  ,content.cardsoftwareRes  ,content.cardfpgaRes  ,content.cardcpldRes  ]]
                f_wcsv.writerows(retlist)
                g_runfinished = g_runfinished + 1
                runtext = "运行中{}/{}".format(g_runfinished,g_total)
                run_labelvalue.set(runtext)


    '''
    
    while not q.empty():
        content = q.get()
        text.insert('end', '\n {}'.format(content))
    '''
    if g_running == True and threading.active_count() == 1:
        text.insert('end', '\n 升级任务完成')
        run_labelvalue.set('升级任务完成')
        g_running = False

    win.after(1000,helpthread,win,text,q)





if __name__ == '__main__':
    multiprocessing.freeze_support()

    win = tkinter.Tk()
    win.title('升级工具')
    win.geometry('900x400')

    frame = tkinter.Frame(win, width=600, height=400, bg='pink')

    frame.pack(side='bottom', pady=50, padx=1, expand=True, fill='both')

    export_button = tkinter.Button(win, text="导入设备文件", bg='skyblue', command=importfile)
    export_button.place(x=30, y=20)

    import_button = tkinter.Button(win, text="升级", bg='skyblue', command=startupgrade)
    import_button.place(x=120, y=20)
    threadnum_label = tkinter.Label(win, text="并发执行线程数",  bg='skyblue')
    threadnum_label.pack()
    threadnum_label.place(x=180, y=20)

    comvalue = tkinter.StringVar()
    comboxlist = ttk.Combobox(win, textvariable=comvalue,width=2)
    comboxlist["values"]=threadnumlist
    comboxlist.current(0)
    comboxlist.pack()
    comboxlist.place(x=280,y=20)

    model_label = tkinter.Label(win, text="每个版本上传后是否自动重启", bg='skyblue')
    model_label.pack()
    model_label.place(x=330, y=20)

    modelcomvalue = tkinter.StringVar()
    modelcomboxlist = ttk.Combobox(win, textvariable=modelcomvalue ,width=3)
    modelcomboxlist["values"] = ['NO','YES']
    modelcomboxlist.current(0)
    modelcomboxlist.pack()
    modelcomboxlist.place(x=500,y=20)

    run_labelvalue = tkinter.StringVar()
    run_labelvalue.set('运行状态')
    run_label = tkinter.Label(win, text="运行状态", bg='skyblue',textvariable=run_labelvalue )
    run_label.pack()
    run_label.place(x=580, y=20)

    # ha_button = tkinter.Button(win, text="getresetcard", bg='skyblue', command=getresetcard)
    # ha_button.place(x=190, y=20)
    l2 = tkinter.Label(frame, text='升级信息回显窗口', font=('微软雅黑', 10, 'bold'), width=500, justify='left',
                       anchor='w')  # justify控制对其方向，anchor控制位置 共同使文本靠左
    l2.place(x=66, y=200)
    l2.pack()
    s2 = tkinter.Scrollbar(frame)  # 设置垂直滚动条
    b2 = tkinter.Scrollbar(frame, orient='horizontal')  # 水平滚动条
    s2.pack(side='right', fill='y')  # 靠右，充满Y轴
    b2.pack(side='bottom', fill='x')  # 靠下，充满x轴

    text = tkinter.Text(frame, font=('Consolas', 9), undo=True, autoseparators=False,
                        wrap='none', xscrollcommand=b2.set,
                        yscrollcommand=s2.set)
    text.place(x=66, y=80)
    text.pack(fill='both', expand='yes')
    text.insert('end', '---升级信息-----')
    s2.config(command=text.yview)  # Text随着滚动条移动被控制移动
    b2.config(command=text.xview)

    win.after(0,helpthread,win,text,msgqueue)
    win.mainloop()

