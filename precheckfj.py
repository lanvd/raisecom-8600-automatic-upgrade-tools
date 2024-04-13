# -*- coding: UTF-8 -*-
import logging
import multiprocessing
import queue
import tkinter
from tkinter import ttk
from netmiko import ConnectHandler, Netmiko
import textfsm
import os
import datetime
from tkinter import messagebox

import tkinter.filedialog
import csv
import chardet
import textfsm
import xlrd
import xlwt

folder_path = './log'
if not os.path.exists(folder_path):
    os.makedirs(folder_path)
logging.basicConfig(filename='log\\dclog.log',level=logging.DEBUG,format='%(asctime)s %(filename)s[line:%(lineno)d] %(message)s',datefmt='%Y-%m-%d %X')
g_devicelist = list()
g_devicelistheadline = ["网元ip","用户名","密码","端口号"]
msgqueue = queue.Queue()
masterKey = ["Shelf", "Slot", "PowerName", "State"]
class EntryPopup(tkinter.Entry):

    def __init__(self, parent, iid, text, **kw):
        ''' If relwidth is set, then width is ignored '''
        super().__init__(parent, **kw)
        self.tv = parent
        self.iid = iid

        self.insert(0, text)
        # self['state'] = 'readonly'
        # self['readonlybackground'] = 'white'
        # self['selectbackground'] = '#1BA1E2'
        self['exportselection'] = False

        self.focus_force()
        self.bind("<Return>", self.on_return)
        self.bind("<Control-a>", self.select_all)
        self.bind("<Escape>", lambda *ignore: self.destroy())

    def on_return(self, event):
        self.tv.item(self.iid, text=self.get())
        self.destroy()

    def select_all(self, *ignore):
        ''' Set selection on the whole text '''
        self.selection_range(0, 'end')

        # returns 'break' to interrupt default key-bindings
        return 'break'



def get_encoding(file):
    # 二进制方式读取，获取字节数据，检测类型
    with open(file, 'rb') as f:
        return chardet.detect(f.read())['encoding']


win = tkinter.Tk()
win.title('升级工具')
win.geometry('900x400')

frame = tkinter.Frame(win, width=600, height=400, bg='pink')
frame.pack(side='bottom', pady=1, padx=1, expand=True)

scorllbary = tkinter.Scrollbar(frame)
scorllbarx = tkinter.Scrollbar(frame, orient=tkinter.HORIZONTAL)
scorllbary.pack(side=tkinter.RIGHT, fill=tkinter.Y)
scorllbarx.pack(side=tkinter.BOTTOM, fill=tkinter.X)

# 定义列名和列的宽度'solt id','PowerName','板块属性',
columns = (
    ('网元ip', 90),
    ('用户名',30),
    ('密码',30),
    ('端口',30),
('solt id', 60),
('PowerName', 60),
('板卡属性', 60),
('硬件版本', 60),
('板卡状态', 60),
    ('bootrom版本', 60),
    ('Software版本', 60),
    ('FPGA版本', 60),
    ('CPLD版本', 60),
      ('升级bootrom文件名', 120),
    ('升级Software文件名', 120),
    ('升级FPGA文件名', 120),
    ('升级CPLD文件名', 120)
)
tree = ttk.Treeview(
    frame,
    height=10,  # treeview显示的行数
    columns=[x[0] for x in columns],
    show='headings',
    yscrollcommand=scorllbary.set,
    xscrollcommand=scorllbarx.set
)
tree.pack(side=tkinter.LEFT, fill=tkinter.BOTH)

mylist = [ ]
info = mylist  # 这里的mylist可以换数据源，比如从SQL获取

for index, data in enumerate(info):
    tree.insert('', tkinter.END, values=data)

scorllbarx.config(command=tree.xview)
scorllbary.config(command=tree.yview)


def set_cell_value(treeview, event):  # 双击进入编辑状态
    for item in treeview.selection():
        # item = I001
        item_text = treeview.item(item, "values")
        # print(item_text[0:2])  # 输出所选行的值
    column = treeview.identify_column(event.x)  # 列
    row = treeview.identify_row(event.y)  # 行
    print('column ={} row ={}'.format(column,row))
    cn = int(str(column).replace('#', ''))
    rn = int(str(row).replace('I', ''))
    pady = 0
    x, y, width, height = treeview.bbox(row, column)
    text = treeview.item(columns[cn][0], 'text')
    treeview.entryPopup = EntryPopup(treeview, cn, text)
    treeview.entryPopup.place(x=0, y=y + pady, anchor=width, relwidth=1)


def treeview_sort_column(tv, col, reverse):  # Treeview、列名、排列方式
    l = [(tv.set(k, col), k) for k in tv.get_children('')]
    # print(tv.get_children(''))
    # print(col)
    # l.sort(reverse=reverse)  # 排序方式
    # l.sort(key=lambda t: int(t[0]), reverse=reverse)  # 排序方式,先转换成数字再排序
    try:
        l.sort(key=lambda t: int(t[0]), reverse=reverse)  # 排序方式,先转换成数字再排序
    except ValueError:
        l.sort(reverse=reverse)  # 排序方式,按文本排序
    for index, (val, k) in enumerate(l):  # 根据排序后索引移动
        tv.move(k, '', index)
        # print(k)
    # print(1) # 测试是否死循环递归
    # 重写标题，使之成为再点倒序的标题，lambda千万不能少，否则就是死循环递归了
    tv.heading(col, text=col, command=lambda: treeview_sort_column(tv, col, not reverse))


for col, width in columns:
    tree.column(col, width=width, anchor=tkinter.CENTER)

columns2 = [x[0] for x in columns]  # 获取列名

for col in columns2:  # 每个列名都加上排序
    treeview_sort_column(tree, col, False)


# 复制选中值(选中的行，list形式复制)
def copy_from_treeview(tree, event):
    selection = tree.selection()
    # column = tree.identify_column(event.x)
    # column_no = int(column.replace("#", "")) - 1
    copy_values = []
    for each in selection:
        try:
            value = tree.item(each)["values"]
            copy_values.append(str(value))
        except:
            pass






def get_desk_p():
    # 获取桌面路径
    return os.path.join(os.path.expanduser('~'), "Desktop")


desk_oath = get_desk_p()
# print(desk_oath)

now = datetime.datetime.now()

excel_columns = ['A1', 'B1', 'C1', 'D1', 'E1', 'F1', 'G1', 'H1', 'I1', 'J1', 'K1', 'L1', 'M1', 'N1', 'O1',
                 'P1', 'Q1', 'R1', 'S1', 'T1', 'U1', 'V1', 'W1', 'X1', 'Y1', 'Z1', 'AA1', 'AB1', 'AC1',
                 'AD1', 'AE1', 'AF1', 'AG1', 'AH1', 'AI1', 'AJ1', 'AK1', 'AL1', 'AM1', 'AN1', 'AO1',
                 'AP1', 'AQ1', 'AR1', 'AS1', 'AT1', 'AU1', 'AV1', 'AW1', 'AX1', 'AY1', 'AZ1']


def export():
    pass
iplist = []
gimportcsvfilename = None
def importfile():
    global gimportcsvfilename
    global g_devicelist
    importcsvfilename = tkinter.filedialog.askopenfilename(title='请选择一个文件',  filetypes=[ ('Excel', '.xls'), \
          ])
    gimportcsvfilename = importcsvfilename

    if importcsvfilename is None or importcsvfilename == '':
        return
    g_devicelist.clear()
    file_encoding = get_encoding(importcsvfilename)
    print('{}文件格式={}'.format(gimportcsvfilename,file_encoding))

    workbook = xlrd.open_workbook(importcsvfilename )
    sheet1 = workbook.sheet_by_index(0)

    print(sheet1.nrows)
    print(sheet1.ncols)
    for ir in range(1, sheet1.nrows):
        row_value = sheet1.row_values(ir)
        row_value = [str(int(item)) if isinstance(item , float) else item for item in row_value]
        print(row_value)
        rowdict = dict(zip(g_devicelistheadline,row_value))
        g_devicelist.append(row_value)
        iplist.append(row_value)
    tree.delete(*tree.get_children())
    for index, data in enumerate(iplist):
        tree.insert('', tkinter.END, values=data)
def getMasterNode(argList):
    for i in argList:
        beginNode = i[0]
        if "*" in beginNode:
            print("find master node =%s" % i)
            masterData = [i[0], i[1], i[4], i[5]]
            return dict(zip(masterKey,masterData ))
    return None
def getBackNode(argList):
    for i in argList:
        PowerName = i[4]
        Begin = i[0]
        if "NXU" in PowerName and "*" not in Begin:
            print("find back node =%s" % i)
            masterData = [i[0], i[1], i[4], i[5]]
            return dict(zip(masterKey,masterData ))
    return None
#cpld boot soft fpga
def getAllVersion(strInfo):
    verList=[]
    print('in{}'.format(strInfo))
    with open('template/cpldversion.template') as template:
        fsm = textfsm.TextFSM(template)
        #print(fsm.header)
        try:
            tmp = fsm.ParseText(strInfo)
            #print(tmp)
            result = tmp[0][0]

            #print(result)
        except Exception as ex:
            #print(ex)
            result = 'ERROR'
            #print(result)
        finally:
            #print('in finally')
            verList.append(result)
    with open('template/bootVersion.template') as template:
        fsm = textfsm.TextFSM(template)
        try:
            tmp = fsm.ParseText(strInfo)
            #print(tmp)
            result = tmp[0][0]
            #print(fsm.header)
            #print(result)
        except Exception as ex:
            #print(ex)
            result = 'ERROR'
            #print(result)
        finally:
            #print('in finally')
            verList.append(result)

    with open('template/softVersion.template') as template:
        fsm = textfsm.TextFSM(template)
        try:

            result = fsm.ParseText(strInfo)
            result = result[0][0]
        #print(fsm.header)
        #print(result)
        except Exception as ex:
            result = 'ERROR'
        finally:
            verList.append(result)
    with open('template/fpgaversion.template') as template:
        fsm = textfsm.TextFSM(template)
        try:

            result = fsm.ParseText(strInfo)
            result = result[0][0]
        #print(fsm.header)
        #print(result)
        except Exception as ex:
            result = 'ERROR'
        finally:
            verList.append(result)
    #print(verList)

    with open('template/hardVersion.template') as template:
        fsm = textfsm.TextFSM(template)
        try:
            result = fsm.ParseText(strInfo)
            result = result[0][0]
        #print(fsm.header)
        #print(result)
        except Exception as ex:
            result = 'None'
        finally:
            verList.append(result)


    logging.debug(verList)
    return verList
def getBusiNode(argList):

    PowerName = argList[4]
    Begin = argList[0]
    if "NXU" not in PowerName:
        print("{}find busi node =%s".format(argList, Begin))
        masterData = [argList[0], argList[1], argList[4], argList[5]]
        return dict(zip(masterKey,masterData))
    return None
def task(neInfo):
    ip=neInfo[0]
    username=neInfo[1]
    passwd=neInfo[2]
    port=neInfo[3]
    retDate = []
    dev_info = {
        'device_type': 'raisecom_telnet',
        'ip': str(ip),
        'username': str(username),
        'password':  str(passwd),
        'secret': str(passwd),
        'session_log': 'log\\netmiko.log',
        'port': int(port)
    }
    print('dev_info={}'.format(dev_info))
    logging.debug('start task == dev_info={}'.format(dev_info))


    net_connect = ConnectHandler(**dev_info)
    command = "show version"
    hardInfo = net_connect.send_command(command)
    hardVersion = ''
    with open('template/hardVersion.template') as template:
        fsm = textfsm.TextFSM(template)
        result = fsm.ParseText(hardInfo)
        hardVersion=result[0][0]

    logging.debug("connect result={}".format(net_connect))
    command = "show card"
    net_connect.enable()
    cardInfo = net_connect.send_command(command)

    logging.debug("cardInfo result={}".format(cardInfo))
    backNode = None
    masterNode = None
    #logging.debug(cardInfo)
    with open('template/showcard.template') as template:
        fsm = textfsm.TextFSM(template)
        result = fsm.ParseText(cardInfo)
        #print(fsm.header)
        #print(result)


        masterNode = getMasterNode(result)
        backNode = getBackNode(result)
        #print(masterNode)
        #logging.debug(masterNode)
        #print(backNode)
        #logging.debug(backNode)
    backDetail = ''
    backverInfo = ''
    if backNode is not None:
        backSlotId = backNode['Slot']
        command = '{} {}'.format('show version slot ', backSlotId)
        print(command)
        backverInfo = net_connect.send_command(command)
        print(backverInfo)
        backDetail = getAllVersion(backverInfo)
        retRow = []
        retRow.append(ip)
        retRow.append(username)
        retRow.append(passwd)
        retRow.append(port)
        retRow.append(backSlotId)
        retRow.append(backNode['PowerName'])
        retRow.append('主控备板')
        retRow.append(backDetail[4])
        retRow.append(backNode['State'])
        retRow.append(backDetail[1])
        retRow.append(backDetail[2])
        retRow.append(backDetail[3])
        retRow.append(backDetail[0])
        retDate.append(retRow)

    masterverInfo = ''
    masterDetail = ''
    if masterNode is not None:
        masterSoltId = masterNode['Slot']
        retRow = []
        command = '{} {}'.format('show version  slot ', masterSoltId)
        print(command)
        masterverInfo = net_connect.send_command(command)
        print(masterverInfo)
        masterDetail = getAllVersion(masterverInfo)
        retRow.append(ip)
        retRow.append(username)
        retRow.append(passwd)
        retRow.append(port)
        retRow.append(masterSoltId)
        retRow.append(masterNode['PowerName'])
        retRow.append('主控板')
        retRow.append(masterDetail[4])
        retRow.append(masterNode['State'])
        retRow.append(masterDetail[1])
        retRow.append(masterDetail[2])
        retRow.append(masterDetail[3])
        retRow.append(masterDetail[0])
        retDate.append(retRow)
    print('begin busi info ')
    # retRow.append(masterverInfo)
    for idata in result:
        idataInfo = getBusiNode(idata)
        if idataInfo is not None:
            soltId = idataInfo['Slot']
            powerName = idataInfo['PowerName']
            powerName = powerName.strip()
            if "iTN" not in powerName:
                continue
            retRow = []
            command = '{} {}'.format('show version  slot ', soltId)
            print(command)
            inodeInfo = net_connect.send_command(command)
            print(inodeInfo)
            inodeInfoDetail = getAllVersion(inodeInfo)
            retRow.append(ip)
            retRow.append(username)
            retRow.append(passwd)
            retRow.append(port)
            retRow.append(soltId)
            retRow.append(powerName)
            retRow.append('业务板')
            retRow.append(inodeInfoDetail[4])
            retRow.append(idataInfo['State'])
            retRow.append(inodeInfoDetail[1])
            retRow.append(inodeInfoDetail[2])
            retRow.append(inodeInfoDetail[3])
            retRow.append(inodeInfoDetail[0])
            retDate.append(retRow)

    logging.debug('task result={}'.format(retDate))
    return  retDate
def error_callback(error):
    logging.debug(f"Error info: {error}")
    print(f"Error info: {error}")

g_finish =0
#--noconsole
def call_back(info):
    global iplist
    global g_finish
    global tree , g_running,result_text
    global msgqueue
    g_finish = g_finish + 1
    logging.debug('查询网元信息个数{} 处理完第{}'.format(len(iplist),g_finish))
    #print('g_finish ={}'.format(g_finish))
    logging.debug('result={}'.format(info))
    msgqueue.put(info)
    for index, data in enumerate(info):
        tree.insert('', tkinter.END, values=data)
        tree.update()


    if g_finish == len(iplist):
        g_finish = 0
        g_running = False


        filename = 'precheck.xls'
        wk = xlwt.Workbook(encoding='utf-8')
        table = wk.add_sheet('预校验结果')


        headLine = ['网元ip', '用户名', '密码', '端口号', 'solt id', 'PowerName', '板卡属性', '硬件版本', '板卡状态',
                    'bootrom版本', 'Software版本', 'FPGA版本', \
                    'CPLD版本', '升级bootrom文件名', '升级Software文件名', '升级FPGA文件名', '升级CPLD文件名','上传完是否重启Y/N' ]

        for i in range(len(headLine)):
            table.write(0, i, headLine[i])
        startLine=1
        while not msgqueue.empty():
            devInfo = msgqueue.get()
            print(devInfo)
            for irow in range(len(devInfo)):
                for icol in range(len(devInfo[irow])):
                    table.write(startLine, icol, devInfo[irow][icol])
                startLine = startLine + 1

        ftptable = wk.add_sheet('服务器信息')
        ftptable.write(0, 0, 'serverip')
        ftptable.write(0, 1, 'user(tftp不填)')
        ftptable.write(0, 2, 'password(tftp不填)')
        ftptable.write(0, 3, 'port(tftp不填)')
        wk.save(filename)

        tkinter.messagebox.showinfo(title="提示", message="网元板卡信息获取完毕")
        result_text.set("网元板卡信息获取完毕，请查看precheck.xls文件")
def precheckne(svcfilename):

    global tree
    global  g_running,gimportcsvfilename
    if g_running:
        tkinter.messagebox.showinfo(title="提示", message="已经启动不需要点击")
        return

    if gimportcsvfilename == None:
        tkinter.messagebox.showinfo(title="提示", message="请选择网元xls文件")
        return
    tree.delete(*tree.get_children())
    result_text.set('板卡信息获取中。。。')
    g_running = True
    pool = multiprocessing.Pool(2)

    k = 0
    for i in iplist:
        k = k + 1

        print(f"开始执行第{i}个任务...")
        logging.debug(f"开始执行第{i}个任务...")
        pool.apply_async(task, args=(i,), callback=call_back, error_callback=error_callback)
    pool.close()
    #pool.join()
def buildimport():
    outfilename = "import_model.xls"
    wk = xlwt.Workbook(encoding='utf-8')
    table = wk.add_sheet('设备列表清单')
    headLine = ['网元ip', '用户名', '密码', '端口号', 'solt id', 'PowerName', '板卡属性', '硬件版本', '板卡状态',
                'bootrom版本', 'Software版本', 'FPGA版本', \
                'CPLD版本', '升级bootrom文件名', '升级Software文件名', '升级FPGA文件名', '升级CPLD文件名' ,'上传完是否重启Y/N' ]
    for i in range(len(headLine)):
        table.write(0, i, headLine[i])
    ftptable = wk.add_sheet('服务器信息')
    ftptable.write(0,0,'serverip')
    ftptable.write(0, 1, 'user(tftp不填)')
    ftptable.write(0, 2, 'password(tftp不填)')
    ftptable.write(0, 3, 'port(tftp不填)')
    wk.save(outfilename)

    tkinter.messagebox.showinfo(title="提示", message="生成导入模板文件import_model.xls")




if __name__ == '__main__':
    multiprocessing.freeze_support()
    g_running = False
    result_text =  tkinter.StringVar()
    export_button = tkinter.Button(win, text="导入预校验文件", bg='skyblue', command=importfile)
    export_button.place(x=30, y=20)

    import_button = tkinter.Button(win, text="预校验网元", bg='skyblue', command= lambda : precheckne( gimportcsvfilename) )
    import_button.place(x=120, y=20)
    build_button = tkinter.Button(win, text="生成导入模板文件", bg='skyblue', command= lambda : buildimport() )
    build_button.place(x=210, y=20)
    result_label = tkinter.Label(win, text="", bg='white', textvariable=result_text)
    result_label.place(x=330, y=20)
    #up_button = tkinter.Button(win, text="升级", bg='skyblue', command=startupgrade)
    #up_button.place(x=200, y=20)

    tree.bind("<Control-Key-c>", lambda x: copy_from_treeview(tree, x))  # 将选中的复制到粘贴板
    tree.bind("<Control-Key-C>", lambda x: copy_from_treeview(tree, x))  # 这里区分大小写，只写小写的话，大C就复制不上

    '''  
    filename = 'precheck.xls'
    wk = xlwt.Workbook(encoding='utf-8')
    table = wk.add_sheet('预校验结果')

    headLine = ['网元ip', '用户名', '密码', '端口号','solt id','PowerName','板卡属性', '硬件版本', '板卡状态','bootrom版本', 'Software版本', 'FPGA版本',\
    'CPLD版本', '升级bootrom文件名',    '升级Software文件名',    '升级FPGA文件名',    '升级CPLD文件名' ,'ftpip','ftpuser','ftppasswd','ftpport']
    for i in range(len(headLine)):
        table.write(0, i, headLine[i])

    wk.save(filename)
    '''
    #win.after(0, helpthread, win,  msgqueue)
    win.mainloop()

