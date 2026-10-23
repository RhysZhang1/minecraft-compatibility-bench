# SPDX-License-Identifier: GPL-3.0-or-later
"""X11 capture/input restricted to our private headless compositor, never DISPLAY."""
import ctypes as C,os,json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
class XImage(C.Structure):
    _fields_=[('width',C.c_int),('height',C.c_int),('xoffset',C.c_int),('format',C.c_int),('data',C.c_void_p),('byte_order',C.c_int),('bitmap_unit',C.c_int),('bitmap_bit_order',C.c_int),('bitmap_pad',C.c_int),('depth',C.c_int),('bytes_per_line',C.c_int),('bits_per_pixel',C.c_int),('red_mask',C.c_ulong),('green_mask',C.c_ulong),('blue_mask',C.c_ulong)]
class Session:
    def __init__(self):
        info=json.loads((ROOT/'runtime/virtual-display.json').read_text());expected=ROOT/'runtime/virtual-session'
        if info.get('XDG_RUNTIME_DIR')!=str(expected) or not (expected/info.get('WAYLAND_DISPLAY','missing')).is_socket():raise ValueError('非项目虚拟显示会话')
        # Verify that the actual compositor is our --virtual process; no desktop fallback.
        pid=int((ROOT/'runtime/display.pid').read_text());argv=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
        if str(ROOT/'scripts/virtual_display.py').encode() not in argv:raise ValueError('虚拟显示进程身份不匹配')
        x=self.x=C.CDLL('libX11.so.6');self.xt=C.CDLL('libXtst.so.6')
        signatures={'XOpenDisplay':(C.c_void_p,[C.c_char_p]),'XDefaultRootWindow':(C.c_ulong,[C.c_void_p]),'XQueryTree':(C.c_int,[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]),'XFetchName':(C.c_int,[C.c_void_p,C.c_ulong,C.POINTER(C.c_void_p)]),'XFree':(C.c_int,[C.c_void_p]),'XGetGeometry':(C.c_int,[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint)]),'XGetImage':(C.POINTER(XImage),[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_ulong,C.c_int]),'XDestroyImage':(C.c_int,[C.POINTER(XImage)]),'XFlush':(C.c_int,[C.c_void_p]),'XSync':(C.c_int,[C.c_void_p,C.c_int]),'XSetInputFocus':(C.c_int,[C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]),'XStringToKeysym':(C.c_ulong,[C.c_char_p]),'XKeysymToKeycode':(C.c_uint,[C.c_void_p,C.c_ulong]),'XQueryPointer':(C.c_int,[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint)]),'XMoveResizeWindow':(C.c_int,[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint]),'XInternAtom':(C.c_ulong,[C.c_void_p,C.c_char_p,C.c_int]),'XChangeProperty':(C.c_int,[C.c_void_p,C.c_ulong,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.c_void_p,C.c_int])}
        signatures['XGetWindowProperty']=(C.c_int,[C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_void_p)])
        for name,(ret,args) in signatures.items():f=getattr(x,name);f.restype=ret;f.argtypes=args
        for name,args in {'XTestFakeKeyEvent':[C.c_void_p,C.c_uint,C.c_int,C.c_ulong],'XTestFakeButtonEvent':[C.c_void_p,C.c_uint,C.c_int,C.c_ulong],'XTestFakeRelativeMotionEvent':[C.c_void_p,C.c_int,C.c_int,C.c_ulong]}.items():getattr(self.xt,name).argtypes=args
        # Errors from a window closing are recoverable, never process-fatal.
        self.error_handler=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)(lambda d,e:0);x.XSetErrorHandler.argtypes=[C.c_void_p];x.XSetErrorHandler(self.error_handler)
        # Empty XAUTHORITY is deliberate: this dedicated Xwayland has its own socket.
        self.ei=C.CDLL(str(ROOT/'input/libgamescaling-ei.so'));self.ei.gs_connect.argtypes=[C.c_char_p,C.c_int];self.ei.gs_motion.argtypes=[C.c_double,C.c_double];self.ei.gs_absolute.argtypes=[C.c_double,C.c_double]
        compositor=[]
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                arguments=(proc/'cmdline').read_bytes().split(b'\0')
                if arguments and Path(os.fsdecode(arguments[0])).name=='kwin_wayland' and b'--virtual' in arguments and b'mc-wayland' in arguments and os.getpgid(int(proc.name))==pid:compositor.append(int(proc.name))
            except (OSError,ValueError):pass
        if len(compositor)!=1:raise ConnectionError('无法唯一确认项目专属合成器')
        if self.ei.gs_connect(info['DBUS_SESSION_BUS_ADDRESS'].encode(),compositor[0])!=0:raise ConnectionError('项目专属libei输入连接失败')
        os.environ['XAUTHORITY']=info.get('XAUTHORITY','')
        self.d=x.XOpenDisplay(info['DISPLAY'].encode())
        if not self.d:raise ConnectionError('无法连接项目专属Xwayland')
        self.root=x.XDefaultRootWindow(self.d);self.window=0;self.held=set();self.width=854;self.height=480
    def children(self,window):
        a=C.c_ulong();b=C.c_ulong();p=C.POINTER(C.c_ulong)();n=C.c_uint()
        if not self.x.XQueryTree(self.d,window,C.byref(a),C.byref(b),C.byref(p),C.byref(n)):return []
        result=list(p[:n.value]);self.x.XFree(p);return result
    def property(self,window,name):
        atom=self.x.XInternAtom(self.d,name.encode(),0);actual=C.c_ulong();fmt=C.c_int();count=C.c_ulong();after=C.c_ulong();data=C.c_void_p()
        self.x.XGetWindowProperty(self.d,window,atom,0,1024,0,0,C.byref(actual),C.byref(fmt),C.byref(count),C.byref(after),C.byref(data))
        if not data.value:return None
        try:
            if fmt.value==32:return list(C.cast(data,C.POINTER(C.c_ulong))[:count.value])
            if fmt.value==8:return C.string_at(data,count.value).decode(errors='replace')
        finally:self.x.XFree(data)
    def title(self,window):
        p=C.c_void_p()
        if not self.x.XFetchName(self.d,window,C.byref(p)) or not p.value:return self.property(window,'_NET_WM_NAME') or ''
        result=C.string_at(p).decode(errors='replace');self.x.XFree(p);return result
    def find(self):
        queue=[(self.root,0)]
        while queue:
            window,depth=queue.pop(0)
            try:client_pid=int((ROOT/'runtime/client.pid').read_text())
            except (OSError,ValueError):client_pid=-1
            if self.property(window,'_NET_WM_PID')==[client_pid] or 'minecraft' in self.title(window).lower():
                if self.window!=window:
                    self.window=window
                    hints=(C.c_ulong*5)(2,0,0,0,0);atom=self.x.XInternAtom(self.d,b'_MOTIF_WM_HINTS',0)
                    self.x.XChangeProperty(self.d,window,atom,atom,32,0,hints,5)
                    self.x.XMoveResizeWindow(self.d,window,0,0,854,480);self.x.XSync(self.d,0)
                self.x.XSetInputFocus(self.d,window,2,0);self.x.XFlush(self.d);return window
            if depth<4:queue.extend((child,depth+1) for child in self.children(window))
        self.window=0;return 0
    def capture(self):
        if not self.window and not self.find():raise ConnectionError('等待虚拟会话中的Minecraft窗口')
        root=C.c_ulong();x=C.c_int();y=C.c_int();w=C.c_uint();h=C.c_uint();border=C.c_uint();depth=C.c_uint()
        if not self.x.XGetGeometry(self.d,self.window,C.byref(root),C.byref(x),C.byref(y),C.byref(w),C.byref(h),C.byref(border),C.byref(depth)):
            self.window=0;raise ConnectionError('Minecraft窗口已关闭')
        im=self.x.XGetImage(self.d,self.window,0,0,w.value,h.value,C.c_ulong(-1).value,2)
        if not im:raise ConnectionError('等待窗口完成首次绘制')
        try:
            v=im.contents
            if v.bits_per_pixel!=32 or v.red_mask!=0xff0000:raise ValueError('暂不支持该XImage像素格式')
            data=C.string_at(v.data,v.bytes_per_line*v.height);self.width=v.width;self.height=v.height
            return Image.frombytes('RGB',(v.width,v.height),data,'raw','BGRX',v.bytes_per_line,1)
        finally:self.x.XDestroyImage(im)
    def cursor(self):
        root=C.c_ulong();child=C.c_ulong();rx=C.c_int();ry=C.c_int();wx=C.c_int();wy=C.c_int();mask=C.c_uint()
        self.x.XQueryPointer(self.d,self.window,C.byref(root),C.byref(child),C.byref(rx),C.byref(ry),C.byref(wx),C.byref(wy),C.byref(mask))
        return {'x':wx.value,'y':wy.value,'button_mask':mask.value}
    def code(self,name):
        names={'Space':'space','Shift':'Shift_L','Ctrl':'Control_L','Esc':'Escape',**dict(zip(['one','two','three','four','five','six','seven','eight','nine'],'123456789'))}
        return self.x.XKeysymToKeycode(self.d,self.x.XStringToKeysym(names.get(name,name.lower()).encode()))
    def apply(self,keys):
        self.ei.gs_pump()
        if not self.ei.gs_ready():raise ConnectionError('虚拟输入设备未就绪')
        keys=set(keys);buttons={'LB':1,'RB':3,'MB':2}
        for name in self.held^keys:
            down=int(name in keys)
            if name in buttons:self.ei.gs_button({'LB':272,'RB':273,'MB':274}[name],down)
            elif (code:=self.code(name)):self.ei.gs_key(code-8,down)
        self.x.XFlush(self.d);self.held=keys
    def center(self):self.ei.gs_absolute(self.width/2,self.height/2)
    def move(self,dx,dy,scroll):
        self.ei.gs_motion(dx*self.width/1000,dy*self.height/1000)
        if scroll:self.ei.gs_scroll(max(-9,min(9,int(scroll))))
        self.x.XFlush(self.d)
