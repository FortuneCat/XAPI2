#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import shelve
import copy
from xapi import *
from xapi.XStruct import *
from xapi.utils import *
from xapi.symbol import *


class MyXSpi(XSpi):
    """
    继承XSpi可以实现回调方法的各种功能
    """

    def __init__(self):
        self.symbols = None

        self.target_position = None
        self.target_position_path = r'd:\y.csv'
        self.target_orders = None

        # 合约
        columns, formats = get_fields_columns_formats(InstrumentField)
        self.instrument_dtype = np.dtype({'names': columns, 'formats': formats})
        self.instrument_dict = {}
        self.instrument_df = pd.DataFrame(columns=columns)
        self.instrument_df_path = r'd:\instrument_df.db'

        # 持仓
        columns, formats = get_fields_columns_formats(PositionField)
        self.position_dtype = np.dtype({'names': columns, 'formats': formats})
        self.position_dict = {}
        self.position_df = pd.DataFrame(columns=columns)
        self.position_df_path = r'd:\position_df.db'

        # 报单
        columns, formats = get_fields_columns_formats(OrderField)
        self.order_dtype = np.dtype({'names': columns, 'formats': formats})
        self.order_dict = {}
        self.order_df = pd.DataFrame(columns=columns)

        # 行情
        self.marketdata_dict = {}
        self.marketdata_dict_path = r'd:\marketdata_dict.db'

        # 行情连接
        self.md = XApi(r'C:\Program Files\SmartQuant Ltd\OpenQuant 2014\XAPI\x86\XAPI_CPP_x86.dll')
        self.md.ServerInfo.Address = br'tcp://180.168.146.187:10010'
        self.md.ServerInfo.BrokerID = b'9999'
        self.md.UserInfo.UserID = b'111'
        self.md.UserInfo.Password = b'123456'

        # 交易连接
        self.td = XApi(r'C:\Program Files\SmartQuant Ltd\OpenQuant 2014\XAPI\x86\XAPI_CPP_x86.dll')
        self.td.ServerInfo.Address = br'tcp://180.168.146.187:10000'
        self.td.ServerInfo.BrokerID = b'9999'
        self.td.UserInfo.UserID = b'111'
        self.td.UserInfo.Password = b'123456'

        # 开启就加载合约信息，这样就用不着每次都查了
        try:
            f = shelve.open(self.instrument_df_path, 'r')
            self.instrument_df = f['instrument_df']
            f.close()
        except:
            pass

            # 是否还要存一份dict，看哪一种方便

    # def OnLog(self, pLog):
    #     # 由于TDX接口的日志太多，屏蔽一下，对于其它软件可能需要打开
    #     pass

    def OnConnectionStatus(self, status, pUserLogin, size1):
        super(MyXSpi, self).OnConnectionStatus(status, pUserLogin, size1)
        pass

    def OnRspQryInstrument(self, pInstrument, size1, bIsLast):
        if size1 <= 0:
            return

        # 一定要用copy,不然最后一个会覆盖前面的
        self.instrument_dict[pInstrument.get_symbol()] = copy.copy(pInstrument)
        if not bIsLast:
            return

        self.instrument_df = ctypes_dict_2_dataframe(self.instrument_dict, self.instrument_dtype)
        self.instrument_df = decode_dataframe(self.instrument_df)
        print(self.instrument_df)

        f = shelve.open(self.instrument_df_path)
        f['instrument_df'] = self.instrument_df
        f.close()

    def OnRspQryInvestorPosition(self, pPosition, size1, bIsLast):
        if size1 <= 0:
            return

        # 一定要用copy,不然最后一个会覆盖前面的
        self.position_dict[pPosition.get_id()] = copy.copy(pPosition)
        if not bIsLast:
            return

        self.position_df = ctypes_dict_2_dataframe(self.position_dict, self.position_dtype)
        self.position_df = decode_dataframe(self.position_df)
        # print(self.position_df)
        print(self.position_df[['Symbol', 'Side', 'Position', 'TodayPosition', 'HistoryPosition']])
        # 每次查询完同时保存，做个记录
        f = shelve.open(self.position_df_path)
        f['position_df'] = self.position_df
        f.close()

    def OnRtnOrder(self, pOrder):
        self.order_dict[pOrder.get_id()] = copy.copy(pOrder)
        print(pOrder)

    def OnRtnDepthMarketData(self, ptr1, size1):
        obj = cast(ptr1, POINTER(DepthMarketDataNField)).contents
        print(obj)
        cp_obj = copy.copy(obj)
        # self.marketdata_dict[obj.get_symbol()] = cp_obj
        # 由于是期货，直接使用合约名就可以定位，这里先这个凑合
        self.marketdata_dict[obj.get_instrument_id()] = cp_obj

        # 先偷懒，不以买卖价为参考
        # # 打印N档行情
        # for i in range(obj.get_ticks_count()):
        #     p = ptr1 + sizeof(DepthMarketDataNField) + sizeof(DepthField) * i
        #     d = cast(p, POINTER(DepthField)).contents
        #     print(d)

    def disconnect(self):
        """
        断开连接
        :return:
        """
        self.td.disconnect()
        self.md.disconnect()

    def connect(self):
        ret = self.md.init(br'C:\Program Files\SmartQuant Ltd\OpenQuant 2014\XAPI\x86\CTP\CTP_Quote_x86.dll')
        if not ret:
            print(self.md.get_last_error())
            exit(-1)

        print(ord(self.md.get_api_type()))
        print(self.md.get_api_name())
        print(self.md.get_api_version())

        ret = self.td.init(br'C:\Program Files\SmartQuant Ltd\OpenQuant 2014\XAPI\x86\CTP\CTP_Trade_x86.dll')
        if not ret:
            print(self.td.get_last_error())
            exit(-1)
        print(ord(self.td.get_api_type()))
        print(self.td.get_api_name())
        print(self.td.get_api_version())
        #
        self.td.register_spi(self)
        self.md.register_spi(self)
        self.td.connect()
        self.md.connect()
        return

    def reconnect(self):
        """
        重连，可能运行过程中出现断线了，这里可以主动重连一下
        :return:
        """
        self.disconnect()
        self.connect()
        return

    def load_positions(self):
        # 表格中东西很多，能否改成只取自己想要的部分？这样在表格合并时就不会出现大量的_x,_y
        self.target_position = pd.read_csv(self.target_position_path, dtype={'Symbol': str})
        print(self.target_position)

    def query_positions(self):
        # 测试使用，用完要注了
        f = shelve.open(self.position_df_path, 'r')
        self.position_df = f['position_df']
        f.close()
        return

        query = ReqQueryField()
        # 查持仓，需要先清空
        self.position_dict = {}
        self.position_df = pd.DataFrame(columns=self.position_dtype.names)
        self.td.req_query(QueryType.ReqQryInvestorPosition, query)

    def query_instruments(self):
        query = ReqQueryField()

        self.instrument_dict = {}
        self.instrument_df = pd.DataFrame(columns=self.instrument_dtype.names)
        self.td.req_query(QueryType.ReqQryInstrument, query)

    def query_account(self):
        query = ReqQueryField()

        self.td.req_query(QueryType.ReqQryTradingAccount, query)

    def sub_quote(self):
        # 期货不用指定交易所，股票需要指定
        a = set()
        b = set()
        if self.target_position is not None:
            a = set(self.target_position['InstrumentID'])
        if self.position_df is not None:
            b = set(self.position_df['InstrumentID'])
        self.symbols = list(a | b)
        print(self.symbols)

        symbols_ = pd.Series(self.symbols).str.encode('gbk')
        for i in range(len(symbols_)):
            self.md.subscribe(symbols_[i], b'')

    def calc_orders(self):
        """
        计算当前持仓与目标持仓的对比图
        :return:
        """
        self.position_df = extend_dataframe_product(self.position_df, self.symbols)
        self.target_position = extend_dataframe_product(self.target_position, self.symbols)

        z = pd.merge(self.position_df, self.target_position, how='outer', on=['InstrumentID', 'Side', 'HedgeFlag'])
        z.fillna(0, inplace=True)
        z['IsSHFE'] = False
        # 需要标记出上期所，对于UFX这种不区分今昨的平台，不要做IsSHFE的修改
        z['IsSHFE'] = list(map(is_shfe, map(get_product, z['Symbol'])))

        self.target_orders = calc_target_orders(z, 'Position_y', 'Position_x')
        return

    def send_orders(self):
        order = (OrderField * 1)()
        orderid = (OrderIDTypeField * 1)()
        orderid[0].OrderIDType = b''

        self.target_orders['InstrumentID_'] = encode_dataframe(self.target_orders[['InstrumentID']])
        self.target_orders['ExchangeID_'] = encode_dataframe(self.target_orders[['ExchangeID']])
        for i in range(len(self.target_orders)):
            row = self.target_orders.iloc[i, :]
            order[0].InstrumentID = row['InstrumentID_']
            order[0].ExchangeID = row['ExchangeID_']
            order[0].Type = OrderType.Limit
            order[0].Side = OrderSide.Buy if row['Buy_Amount'] > 0 else OrderSide.Sell
            order[0].Qty = abs(row['Buy_Amount'])
            order[0].OpenClose = OpenCloseType.Open
            if row['Open_Amount'] < 0:
                order[0].OpenClose = OpenCloseType.Close
                if row['CloseToday_Flag'] == 1:
                    order[0].OpenClose = OpenCloseType.CloseToday

            try:
                tickSize = self.instrument_df[row['InstrumentID']].PriceTick
            except:
                tickSize = 1

            marketdata = None
            try:
                marketdata = self.marketdata_dict[row['InstrumentID']]
                price = marketdata.LastPrice
            except:
                print('%s,没有价格' % row['InstrumentID'])
                continue

            # 自己修改是挂单还是吃单
            if row['Buy_Amount'] > 0:
                price -= 2 * tickSize
            else:
                price += 2 * tickSize

            # 是否进行涨跌停修正
            if marketdata is not None:
                price = min(price, marketdata.UpperLimitPrice)
                price = max(price, marketdata.LowerLimitPrice)

            order[0].Price = price
            # 下单
            ret = self.td.send_order(order[0], orderid[0], 1)
            print('orderid:%s' % ret)

        return

    def cancel_orders(self):
        """
        批量撤单
        :return:
        """
        orderid = (OrderIDTypeField * 2)()
        orderid[0].OrderIDType = b''
        orderid[1].OrderIDType = b''

        for k, v in self.order_dict.items():
            # 只要有挂单就可以撤
            # LeavesQty是剩余数量，CumQty是成交数量，没有撤单信息，所以这个值永远等于0
            left_qty = v.Qty - v.CumQty - v.LeavesQty
            # 只能通过集合来进行撤单了
            if v.Status not in {OrderStatus.Rejected, OrderStatus.Cancelled, OrderStatus.Filled}:
                orderid[0].OrderIDType = v.ID
                self.td.cancel_order(orderid[0], orderid[1], 1)

    def print_orders(self):
        # 这里是否订单太多，能否只显示一部分呢？
        print(self.order_dict.values())

    def usage(self):
        # 1. 在保证没有挂单的前提下，再次查询持仓，计算仓差然后补单
        # 2. 生成委托单列表后，再下单时根据列表的完成度进行补单，这种方法下单比较快，但代码复杂，先不实现
        print(u'1 - 读取目标仓位')
        print(u'2 - 查询实盘仓位')
        print(u'3 - 两仓位归集后，订阅行情')
        print(u'4 - 计算交易清单,显示进度')
        print(u'5 - 批量下单')
        print(u'6 - 利用回报批量撤单')
        print(u'q - 退出')
        print(u'10 - 查合约列表，得到最小变动价位，并保存')
        print(u'11 - 查资金')
        print(u'12 - 打印订单')
        print(u'100 - 重连')

    def input(self, x):
        _menu = {
            1: self.load_positions,
            2: self.query_positions,
            3: self.sub_quote,
            4: self.calc_orders,
            5: self.send_orders,
            6: self.cancel_orders,
            10: self.query_instruments,
            11: self.query_account,
            12: self.print_orders,
            100: self.reconnect,
        }

        _menu.get(i, self.usage)()


if __name__ == '__main__':
    print(sys.stdin.encoding)
    spi = MyXSpi()
    spi.connect()

    while True:
        spi.usage()
        x = input('')

        # 输入数字时，python3是str，python2是int，需要处理一下
        print(x)
        print(type(x))

        if x == "q":
            break

        # 处理输入是回车或别符号的可能性
        try:
            i = int(x)
        except:
            continue

        spi.input(x)

    # 循环外，退出
    spi.disconnect()
