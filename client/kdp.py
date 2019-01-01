
import serial
import sys,tty,termios
from struct import pack,unpack
from binascii import hexlify,unhexlify

class _Getch:
    def __call__(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            if (ch == '\x1b'):
                ch += sys.stdin.read(1)
                if (ch == '\x1b['):
                    ch += sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch

class funcdef:
    addr = 0x0
    retType = "int"
    name = "func"
    argcnt = 2
    unsled = 1
    def __init__(self,addr,ret,name,args,unsled=1):
        self.addr = addr
        self.ret = ret
        self.name = name
        self.args = args
        self.unsled = unsled

class cKDP:
    ser = None
    isRunning = 0
    inputs = []
    myfuncs = {}
    hooks = {}

    #kdp vars
    readDebug = 0
    kbase = None
    kslide = None

    def __init__(self,serialfile = "/dev/tty.usbserial-AD025J9F", baud = 115200):
        self.ser = serial.serial_for_url(serialfile, do_not_open=True)
        self.ser.baudrate = baud
        self.ser.timeout = 5

    def open(self):
        self.ser.open()

    def close(self):
        self.ser.close()

    def wait(self):
        self.kdpWrite("i")
        conf = self.kdpRead(1);
        if conf:
            self.initKDP(conf)
            return
        print "Waiting for debugger hello message..."
        buf = ""
        while (len(buf) < len("helloPDK") or buf[-len("helloPDK"):] != "helloPDK"):
            c = self.serialRead(1)
            if not len(c):
                continue
            sys.stdout.write(c)
            # sys.stdout.flush()
            buf +=c
        sys.stdout.write("\n")
        while (len(buf) < len("donePDK") or buf[-len("donePDK"):] != "donePDK"):
            c = self.serialRead(1)
            if not len(c):
                continue
            buf +=c
        self.initKDP(buf.split("helloPDK")[1].split("donePDK")[0])

    def start(self):
        if not self.kbase:
            kdp.initKDP()
        self.isRuning = 1
        while self.isRuning:
            self.shell()

    #tools
    def hexdump(self, adr, src, length=16, linePrefix = ""):
        FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])
        lines = []
        unichr_ = unichr
        for c in xrange(0, len(src), length):
            chars = src[c:c+length]
            try:
                unichr(chars[0])
            except TypeError:
                def _t(v):
                    return v
                unichr_ = _t
            hex = ' '.join(["%02x" % ord(unichr_(x)) for x in chars])
            printable = ''.join(["%s" % ((ord(unichr_(x)) <= 127 and FILTER[ord(unichr_(x))]) or '.') for x in chars])
            lines.append(linePrefix + "0x%08x  %-*s  %s\n" % (adr + c, length*3, hex, printable))
        print ''.join(lines)

    def toInt(self,adr):
        if (type(adr) == int):
            return adr
        if len(adr.split("0x")) == 2:
            adr = int(adr,16)
        else:
            adr = int(adr)
        return adr

    def addFunc(self, func):
        self.myfuncs[func.name] = func
        fdec = "added function " + func.ret +" "+ func.name + "("
        c = ord('a')
        for i in range(func.args):
            fdec += chr(c) + ", "
            c+=1
        fdec = fdec[0:-2] + ")"
        print fdec

    #input handling
    def getInput(self):
        c = ''
        i = 0
        p = 0
        def printInput():
            sys.stdout.write("\x1b[2K\r"+"$ "+self.inputs[i])
            j = len(self.inputs[i]) - p
            while j>0:
                sys.stdout.write("\b")
                j-=1


        if (len(self.inputs) <1 or self.inputs[0] != ""):
            self.inputs.insert(0,"")
        sys.stdout.write('$ ')
        inkey = _Getch()
        while(1):
            k=inkey()
            if k == '\x03':
                print ""
                quit()
            elif k=='\x1b[A': #up
                if (i >= len(self.inputs)-1):
                    continue
                i+=1
                p = len(self.inputs[i])
                printInput()
            elif k=='\x1b[B': #down
                if (i==0):
                    continue
                i-=1
                p = len(self.inputs[i])
                printInput()
            elif k=='\x1b[C': #right
                if (p < len(self.inputs[i])):
                    sys.stdout.write(self.inputs[i][p])
                    p+=1
            elif k=='\x1b[D': #left
                if (p>0):
                    sys.stdout.write("\b")
                    p-=1
            elif k == '\n' or k == '\r':
                print ""
                break
            elif k == '\x7f': #backspace
                if (p>0):
                    self.inputs[i] = self.inputs[i][0:p-1] + self.inputs[i][p:]
                    p-=1
                    printInput()
            else:
                self.inputs[i] = self.inputs[i][0:p] + k + self.inputs[i][p:]
                p +=1
                printInput()
        if (not len(self.inputs[i]) and len(self.inputs) > 1):
            return self.inputs[i+1]
        return self.inputs[i]

    #kdp
    def serialWrite(self, what):
        if len(what) > 24:
            what = what[0:24] + "D" + what[24:] #weird bug loses 1 char at that pos
        self.ser.write(what)
    def serialRead(self, size):
        return self.ser.read(size)

    def kdpWrite(self,msg,verbose=0):
        if verbose:
            print "sending=\"%s\"" %msg
        self.serialWrite("helloKDP"+msg+"doneKDP")

    def kdpRead(self, quiet=0):
        buf = ""
        while (len(buf) < len("helloPDK") or buf[-len("helloPDK"):] != "helloPDK"):
            c = self.serialRead(1)
            if self.readDebug:
                sys.stdout.write(c)
            if not len(c):
                if not quiet:
                    print "kdpRead failed to read helloPDK"
                return None
            buf +=c
        if self.readDebug:
            sys.stdout.write('\n')
        buf = ""
        while (len(buf) < len("donePDK") or buf[-len("donePDK"):] != "donePDK"):
            c = self.serialRead(1)
            if self.readDebug:
                sys.stdout.write(c)
            if not len(c):
                if not quiet:
                    print buf
                    print "kdpRead failed to read donePDK"
                return None
            buf +=c
        if self.readDebug:
            sys.stdout.write('\n')
        buf = buf[0:-len("donePDK")]
        if "error=" in buf:
            for e in buf.split("error="):
                e = e.split(";")[0]
                if not len(e):
                    continue
                if not quiet:
                    print "Deviceerror: "+e
        return buf.split(";")[-1]

    def setConfig(self,key,val):
        if (key == "kbase"):
            self.kbase = unpack("<I",unhexlify(val))[0]
            if self.kbase % 0x1000 == 0xf00:
                self.kbase += 0x100
            self.kslide = self.kbase - 0x80001000
        else:
            print "Error: unknown config key=\"%s\"" %key

    def parseConf(self,conf):
        rt = []
        for c in conf.split("|"):
            if not len(c):
                continue
            key,val = c.split("=")
            rt.append({key : val})
        return rt

    def initKDP(self, conf = None):
        if (not conf):
            self.kdpWrite("i")
            conf = self.kdpRead();
        if (not conf):
            print "Error: getting conf failed"
            return None
        if (not conf.startswith("initKDP")):
            print "Error: initKDP not found in=\"%s\"" %conf
            return None
        conf = conf[len("initKDP"):]
        for c in self.parseConf(conf):
            key = c.keys()[0]
            val = c[key]
            self.setConfig(key,val)
        print "Initialising Serial Debugger done!"
        print "Kernelbase=%s" % hex(self.kbase)

    def ksled(self,ptr):
        if not self.kslide:
            print "Error: kernelslide not set"
            return None
        return ptr+self.kslide

    def kunsled(self,ptr):
        if not self.kslide:
            print "Error: kernelslide not set"
            return None
        return ptr-self.kslide

    def memRead(self, ptr, size):
        rsrc = hexlify(pack("<I",ptr))
        rsz = hexlify(pack("<I",size))
        self.kdpWrite("r"+rsrc+rsz)
        red = self.kdpRead()
        redSize = unpack("<I",unhexlify(red[-8:]))[0]
        red = unhexlify(red[0:-8])
        if (redSize != size):
            print "WARNING: requested readSize and actual readSize mismatch!"
            print "         requested=%s but actual=%s" %(hex(size),hex(redSize))
        return red,redSize

    def memWriteUnchecked(self, ptr, data):
        rptr = hexlify(pack("<I",ptr))
        rlen = hexlify(pack("<I",len(data)/2))
        try:
            unhexlify(data)
        except TypeError:
            print "Error: hexdata invalid"
            return None
        self.kdpWrite("w"+rptr+rlen+data)
        red = self.kdpRead()
        rsp = self.parseConf(red)
        wrt = unpack("<I",unhexlify(rsp[0]["wroteData"]))[0]
        if (len(data)/2 != wrt):
            print "WARNING: written bytes and size of sent data mismatch!"
            print "         requested=%s but actual=%s" %(hex(len(data)/2),hex(redSize))
        return wrt

    def memWrite(self, ptr, data):
        wrt = 0
        blockSize = 0x100
        dataSize = len(data)
        if (dataSize % 2):
            print "Error: hexdata invalid"
            return None
        dataSize /=2

        while wrt < dataSize:
            gesBlock = dataSize/blockSize
            if dataSize%blockSize:
                gesBlock += 1
            curblock = (wrt/blockSize)+1
            wdata = data[wrt*2:wrt*2+blockSize*2]
            rr = self.memWriteUnchecked(ptr,wdata)
            if gesBlock>1:
                print "done writing block %d of %d" %(curblock,gesBlock)
            if not rr:
                return None
            wrt += rr
            ptr += rr
            if rr != len(wdata)/2 and curblock < gesBlock:
                print "Error: got incorrect data write. Aborting"
                break
        print "wrote %s bytes" %hex(wrt)

    def executeFunction(self, ptr, params, unsled=0):
        if len(params) and not len(params[0]):
            params.remove(params[0])
        if (len(params) > 10):
            print "Error: too many params"
            return None

        try:
            for i in range(len(params)):
                params[i] = self.toInt(params[i])
        except:
            print "Error: parsing parameters failed"
            return None
        addr = 0
        try:
            addr = self.toInt(ptr)
        except:
            if not ptr in self.myfuncs:
                print "Error: function \"%s\" not found" %name
                return None
            func = self.myfuncs[ptr]
            addr = func.addr
            unsled = func.unsled
            if len(params) != func.args:
                print "Error: function expects %d parameters, but given %d" %(func.args,len(params))
                return None
        if unsled:
            addr = self.ksled(addr)
        rptr = hexlify(pack("<I",addr))
        rcnt = hexlify(pack("<B",len(params)))
        rparams = ""
        for p in params:
            rparams += hexlify(pack("<I",p))
        print "executing %s" %str(ptr)
        self.kdpWrite("x"+rptr+rcnt+rparams)
        red = self.kdpRead()
        rsp = self.parseConf(red)
        rret = unpack("<I",unhexlify(rsp[0]["return"]))[0]
        return rret

    def addhook(self,name,func,paramCnt):
        self.hooks[name] = [func,paramCnt]

    def runhook(self,name,params):
        if not name in self.hooks:
            print "Error: unknown hook"
            return None
        h = self.hooks[name]
        if len(params) != h[1]:
            print "Error: bad parameter count"
            return None
        return h[0](self,params)

    #running
    def shell(self):
        input = self.getInput()
        sps = input.split(" ")
        if (sps[0][0] == "r" and len(sps)>2):
            ptr = self.toInt(sps[1])
            prefix = ""
            if sps[0] == "rv":
                ptr = self.ksled(ptr)
                prefix = "unsled "
            mem, memSize = self.memRead(ptr,self.toInt(sps[2]))
            if mem:
                self.hexdump(self.toInt(sps[1]),mem,16,prefix)
            else:
                print "reading mem failed"
        elif (sps[0][0] == "w" and len(sps)>2):
            ptr = self.toInt(sps[1])
            if sps[0] == "wv":
                ptr = self.ksled(ptr)
            tmp = input.replace("  "," ")
            while len(input) != len(tmp):
                tmp = input = input.replace("  "," ")
            sps = input.split(" ")
            self.memWrite(self.toInt(ptr),sps[2])
        elif sps[0].startswith("call"):
            v = 0
            if sps[0] == "callv":
                v = 1
            elif sps[0] != "call":
                print "Error: unknown call command"
                return
            prm = input[len(sps[0])+1:]
            name = prm.split("(")[0]
            params = prm.split("(")[1].split(")")[0].replace(" ","").split(",")
            print "return="+hex(self.executeFunction(name,params,v))
        elif sps[0].startswith("func"):
            if sps[0] != "func":
                print "Error: unknown func command"
                return
            prm = input[len(sps[0])+1:]
            name = prm.split("(")[0]
            params = prm.split("(")[1].split(")")[0].replace(" ","").split(",")
            rt = self.runhook(name,params)
            if not rt:
                print "An error occured!"
            else:
                print "return="+hex(rt)
        elif (sps[0] == "raw"):
            arg = input[len(sps[0])+1:]
            self.kdpWrite(arg)
            print "got=\""+self.kdpRead()+"\""
        elif (sps[0] == "config"):
            print "Kernelbase="+hex(self.kbase)
            print "Kernelslide="+hex(self.kslide)
        else:
            print "unknown command \"%s\"" %input



#main
def proc_find(ctx,params):
    uaddr = ctx.ksled(0x80001000 + 0x45f2c8)
    pid = ctx.toInt(params[0])
    proc,sz = ctx.memRead(uaddr,0x4)
    if sz != 4:
        print "Error: bad read size"
        return None
    proc = unpack("<I",proc)[0]
    sptr = proc
    while True:
        pids,sz = ctx.memRead(sptr+8,0x4)
        cpid = unpack("<I",pids)[0]
        if (cpid == pid):
            proc,sz = ctx.memRead(sptr+12,0x4)
            return unpack("<I",proc)[0]
        sptrs,sz = ctx.memRead(sptr,0x4)
        sptr = unpack("<I",sptrs)[0]
        if not sptr:
            print "Error: proccess with pid %d not found" %pid
            return None
    return 0

kdp = cKDP()
try:
    kdp.open()
except serial.SerialException as e:
    sys.stderr.write('Could not open serial port {}: {}\n'.format(ser.name, e))
    sys.exit(1)

kdp.serialWrite("AASDASDA")
print hexlify(kdp.serialRead(8))
print "ok"

if (len(sys.argv) > 1 and sys.argv[1] == "--wait"):
    kdp.wait()

kdp.addFunc(funcdef(0x800cdbc8,"char*","strlen",1))
kdp.addhook("proc_find", proc_find ,1)
kdp.start()


kdp.close()
