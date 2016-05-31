from __future__ import absolute_import
from __future__ import print_function

import veriloggen.core.vtypes as vtypes
import veriloggen.core.module as module

class BramInterface(object):
    _I = 'Reg'
    _O = 'Wire'
    
    def __init__(self, m, name=None, datawidth=32, addrwidth=10, itype=None, otype=None,
                 p_addr='addr', p_rdata='rdata', p_wdata='wdata', p_wenable='wenable',
                 index=None):
    
        if itype is None:
            itype = self._I
        if otype is None:
            otype = self._O
            
        self.m = m

        name_addr = p_addr if name is None else '_'.join([name, p_addr])
        name_rdata = p_rdata if name is None else '_'.join([name, p_rdata])
        name_wdata = p_wdata if name is None else '_'.join([name, p_wdata])
        name_wenable = p_wenable if name is None else '_'.join([name, p_wenable])

        if index is not None:
            name_addr = name_addr + str(index)
            name_rdata = name_rdata + str(index)
            name_wdata = name_wdata + str(index)
            name_wenable = name_wenable + str(index)

        if itype == 'Reg' or itype == 'OutputReg':
            self.addr = getattr(m, itype)(name_addr, addrwidth, initval=0)
        else:
            self.addr = getattr(m, itype)(name_addr, addrwidth)
            
        if otype == 'Reg' or otype == 'OutputReg':
            self.rdata = getattr(m, otype)(name_rdata, datawidth, initval=0)
        else:
            self.rdata = getattr(m, otype)(name_rdata, datawidth)
            
        if itype == 'Reg' or itype == 'OutputReg':
            self.wdata = getattr(m, itype)(name_wdata, datawidth, initval=0)
            self.wenable = getattr(m, itype)(name_wenable, initval=0)
        else:
            self.wdata = getattr(m, itype)(name_wdata, datawidth)
            self.wenable = getattr(m, itype)(name_wenable)

    def connect(self, targ):
        self._connect_port(self.addr, targ.addr)
        self._connect_port(targ.rdata, self.rdata)
        self._connect_port(self.wdata, targ.wdata)
        self._connect_port(self.wenable, targ.wenable)

    def _connect_port(self, left, right):
        if isinstance(left, vtypes.Reg):
            left.module.Always()( left(right, blk=True) )
        else:
            left.assign(right)

class BramSlaveInterface(BramInterface):
    _I = 'Input'
    _O = 'Output'

class BramMasterInterface(BramInterface):
    _I = 'Output'
    _O = 'Input'

#-------------------------------------------------------------------------------    
def mkBramDefinition(name, datawidth=32, addrwidth=10, numports=2):
    m = module.Module(name)
    clk = m.Input('CLK')
    
    interfaces = []
    
    for i in range(numports):
        interface = BramSlaveInterface(m, name + '_%d'%i, datawidth, addrwidth)
        interface.delay_addr = m.Reg(name + '_%d_daddr' % i, addrwidth)
        interfaces.append(interface)

    mem = m.Reg('mem', datawidth, length=2**addrwidth)

    for interface in interfaces:
        m.Always(vtypes.Posedge(clk))(
            vtypes.If(interface.wenable)(
                mem[interface.addr](interface.wdata)
            ),
            interface.delay_addr(interface.addr)
        )
        m.Assign(interface.rdata(mem[interface.delay_addr]))

    return m

#-------------------------------------------------------------------------------    
class Bram(object):
    def __init__(self, m, name, clk, rst, datawidth=32, addrwidth=10, numports=2):
        self.m = m
        self.clk = clk
        self.rst = rst
        self.datawidth = datawidth
        self.addrwidth = addrwidth
        self.interfaces = [ BramInterface(m, name + '_%d'%i, datawidth, addrwidth)
                            for i in range(numports) ]
        
        self.definition = mkBramDefinition(name, datawidth, addrwidth, numports)
        self.inst = self.m.Instance(self.definition, 'inst_' + name,
                                    ports=m.connect_ports(self.definition))

    def __getitem__(self, index):
        return self.interfaces[index]

    def write(self, mng, port, addr, wdata, cond=None):
        """ Write operation with Seq or FSM object as mng """
        if cond is not None:
            mng.If(cond)
            
        mng(
            self.interfaces[port].addr(addr),
            self.interfaces[port].wdata(wdata),
            self.interfaces[port].wenable(1)
        )
        mng.then.Delay(1)(
            self.interfaces[port].wenable(0)
        )

    def read(self, mng, port, addr, rdata=None, rvalid=None, cond=None):
        """ Read operation with Seq or FSM object as mng """
        if cond is not None:
            mng.If(cond)
            
        mng(
            self.interfaces[port].addr(addr)
        )

        if rdata is not None:
            mng.then.Delay(2)(
                rdata(self.interfaces[port].rdata)
            )
        else:
            rdata = self.interfaces[port].rdata
            
        if rvalid is not None:
            mng.then.Delay(2)(
                rvalid(1)
            )
            mng.then.Delay(3)(
                rvalid(0)
            )
        else:
            rvalid = self.m.TmpReg(initval=0)
            mng.then.Delay(1)(
                rvalid(1)
            )
            mng.then.Delay(2)(
                rvalid(0)
            )

        return rdata, rvalid