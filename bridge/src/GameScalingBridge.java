package local.gamescaling;

import cpw.mods.fml.common.Mod;
import cpw.mods.fml.common.Mod.EventHandler;
import cpw.mods.fml.common.event.FMLInitializationEvent;
import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import cpw.mods.fml.common.gameevent.TickEvent;
import com.google.gson.*;
import java.lang.reflect.*;
import java.nio.*;
import java.nio.file.*;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import java.util.*;
import gsinput.VirtualInput;

/** Client-local actions only: this mod never injects operating-system input. */
@Mod(modid="gamescalingbridge",name="GameScaling local bridge",version="1.0",acceptableRemoteVersions="*")
public class GameScalingBridge {
    private final Path root=Paths.get(System.getProperty("gamescaling.bridge","gamescaling-bridge"));
    private final Gson gson=new Gson();
    private long lastFrame=0,lastStatus=0,lastConnect=0,started=0,lastId=-1;
    private JsonObject action=null;
    private String error="";
    private Object mc;
    private int cursorX=427,cursorY=240;
    private long lastProbe=-1;
    private Set<Integer> held=new HashSet<Integer>();
    private Set<Integer> guiMouseHeld=new HashSet<Integer>();
    private JsonObject packetTarget=null,miningTarget=null;
    private long actionEpoch=-1,miningEpoch=-1,miningStarted=0,miningDeadline=0;
    private String miningStop="",telemetryError="";
    private int renderedFrames=0;
    private long fpsSince=System.currentTimeMillis();
    private double renderFps=0;
    private void report(Throwable ex){
        while(ex instanceof InvocationTargetException&&ex.getCause()!=null)ex=ex.getCause();
        String msg=ex.toString();if(!msg.equals(error))ex.printStackTrace();error=msg;
    }
    private static Field field(Class<?> c,String... names)throws Exception {
        for(Class<?> k=c;k!=null;k=k.getSuperclass()) for(String n:names)
            try {Field f=k.getDeclaredField(n);f.setAccessible(true);return f;}catch(NoSuchFieldException e){}
        throw new NoSuchFieldException(c.getName()+Arrays.toString(names));
    }
    private static Object get(Object o,String... ns)throws Exception{return field(o.getClass(),ns).get(o);}
    private static Method method(Class<?> c,String[] ns,Class<?>... args)throws Exception {
        for(Class<?> k=c;k!=null;k=k.getSuperclass())for(String n:ns)
            try{Method m=k.getDeclaredMethod(n,args);m.setAccessible(true);return m;}catch(NoSuchMethodException e){}
        throw new NoSuchMethodException(c.getName()+Arrays.toString(ns));
    }
    private static Class<?> cls(String n)throws Exception{return Class.forName(n);}
    private void json(String name,JsonObject value)throws Exception{
        Path p=root.resolve(name),tmp=root.resolve(name+".tmp");
        Files.write(tmp,gson.toJson(value).getBytes("UTF-8"));
        Files.move(tmp,p,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
    }
    @EventHandler public void init(FMLInitializationEvent e)throws Exception {
        if(e.getSide().isClient()){
            // Resolve both shims now so missing/unsupported isolation fails before actions.
            cls("org.lwjglx.input.Mouse");cls("org.lwjglx.input.Keyboard");
            if(!VirtualInput.ready())throw new IllegalStateException("Input isolation hooks are not ready");
            Files.createDirectories(root);
            Path prior=root.resolve("command.json");
            if(Files.exists(prior)){
                try{lastId=gson.fromJson(new String(Files.readAllBytes(prior),"UTF-8"),JsonObject.class).get("id").getAsLong();}catch(Exception ignored){}
            }
            FMLCommonHandler.instance().bus().register(this);
            System.out.println("[GameScaling] local bridge initialized: "+root);
        }
    }
    @SubscribeEvent public void tick(TickEvent.ClientTickEvent e){
        if(e.phase!=TickEvent.Phase.END)return;
        try {
            if(mc==null)mc=method(cls("net.minecraft.client.Minecraft"),new String[]{"func_71410_x","getMinecraft"}).invoke(null);
            Object world=get(mc,"field_71441_e","theWorld");
            Object screen=get(mc,"field_71462_r","currentScreen");
            long now=System.currentTimeMillis();
            if(world==null&&screen!=null&&(screen.getClass().getSimpleName().equals("GuiMainMenu")||screen.getClass().getSimpleName().equals("GuiCustom")||screen.getClass().getSimpleName().equals("GuiDisconnected"))&&now-lastConnect>30000){
                lastConnect=now;
                Class<?> fml=cls("cpw.mods.fml.client.FMLClientHandler");
                Object handler=fml.getMethod("instance").invoke(null);
                fml.getMethod("connectToServerAtStartup",String.class,int.class).invoke(handler,"127.0.0.1",25565);
            }
            Object player=get(mc,"field_71439_g","thePlayer");
            if((action!=null&&actionEpoch>=0&&!leaseValid(actionEpoch,now))||
               (miningTarget!=null&&!leaseValid(miningEpoch,now))){
                finishMining("control changed or heartbeat expired",true);
                if(action!=null){complete(now,true);action=null;}
            }
            if(miningTarget!=null){
                String reason=world==null||player==null?"disconnected":screen!=null?"GUI opened":
                    now>=miningDeadline?"maximum hold reached":
                    !miningTarget.equals(targetBlock())?"target changed or block broken":"";
                if(!reason.isEmpty())finishMining(reason,true);
            }
            Path probe=root.resolve("input-probe.json");
            if(Files.exists(probe)&&action==null){
                long probeId=gson.fromJson(new String(Files.readAllBytes(probe),"UTF-8"),JsonObject.class).get("id").getAsLong();
                if(probeId>lastProbe){lastProbe=probeId;probeInput(probeId);}
            }
            if(player!=null){
                if(((Number)get(player,"field_70725_aQ","deathTime")).intValue()>20)
                    method(player.getClass(),new String[]{"func_71004_bE","respawnPlayer"}).invoke(player);
            }
            Path command=root.resolve("command.json");
            if(Files.exists(command)){
                JsonObject a=gson.fromJson(new String(Files.readAllBytes(command),"UTF-8"),JsonObject.class);
                long id=a.get("id").getAsLong();
                if(id>lastId&&action==null){
                    finishMining("next model action",false);
                    lastId=id;action=a;started=now;error="";
                    actionEpoch=a.has("epoch")?a.get("epoch").getAsLong():-1;
                    if(actionEpoch>=0&&!leaseValid(actionEpoch,now)){
                        apply(new HashSet<Integer>());complete(now,true);action=null;return;
                    }
                    if(player!=null&&screen==null){
                        JsonArray mouse=a.getAsJsonArray("mouse");
                        float dx=mouse.get(0).getAsFloat(),dy=mouse.get(1).getAsFloat();
                        // A packet's normalized pixel delta -> vanilla mouse sensitivity rotation.
                        int w=((Number)get(mc,"field_71443_c","displayWidth")).intValue();
                        int h=((Number)get(mc,"field_71440_d","displayHeight")).intValue();
                        method(player.getClass(),new String[]{"func_70082_c","setAngles"},float.class,float.class).invoke(player,dx*w/1000f,-dy*h/1000f);
                        int scroll=mouse.get(2).getAsInt();
                        if(scroll!=0){Object inv=get(player,"field_71071_by","inventory");
                            method(inv.getClass(),new String[]{"func_70453_c","changeCurrentItem"},int.class).invoke(inv,scroll);}
                    } else if(screen!=null) {
                        JsonArray mouse=a.getAsJsonArray("mouse");
                        int w=((Number)get(mc,"field_71443_c","displayWidth")).intValue();
                        int h=((Number)get(mc,"field_71440_d","displayHeight")).intValue();
                        cursorX=Math.max(0,Math.min(w-1,cursorX+Math.round(mouse.get(0).getAsFloat()*w/1000f)));
                        cursorY=Math.max(0,Math.min(h-1,cursorY+Math.round(mouse.get(1).getAsFloat()*h/1000f)));
                        // Keep the emulated mouse in this client only. GLFW cursor
                        // warping is unavailable on some lwjgl3ify/Wayland paths.
                        Class<?> mouseClass=cls("org.lwjglx.input.Mouse");
                        for(String name:new String[]{"x","latestX"})field(mouseClass,name).setInt(null,cursorX);
                        for(String name:new String[]{"y","latestY"})field(mouseClass,name).setInt(null,h-cursorY-1);
                    }
                    // Deliver the first pulse immediately: waiting for the next
                    // rendered frame can otherwise skip a single 33ms GUI click.
                    Set<Integer> first=new HashSet<Integer>();
                    if(a.getAsJsonArray("steps").size()>0)
                        for(JsonElement k:a.getAsJsonArray("steps").get(0).getAsJsonArray()){int n=key(k.getAsString());if(n!=0)first.add(n);}
                    apply(first);
                    packetTarget=world!=null&&screen==null?targetBlock():null;
                }
            }
            if(now-lastStatus>500){lastStatus=now;JsonObject state=new JsonObject();
                state.addProperty("timestamp",now);state.addProperty("connected",world!=null&&player!=null);
                state.addProperty("screen",screen==null?"":screen.getClass().getSimpleName());
                state.addProperty("command_id",lastId);state.addProperty("busy",action!=null);state.addProperty("error",error);
                state.addProperty("mining_active",miningTarget!=null);state.addProperty("mining_stop",miningStop);
                if(miningTarget!=null){state.add("mining_target",miningTarget);state.addProperty("mining_elapsed_ms",now-miningStarted);}
                state.addProperty("render_fps",Math.round(renderFps*10)/10.0);
                try{
                    Object options=get(mc,"field_71474_y","gameSettings");
                    state.addProperty("render_distance",((Number)get(options,"field_151451_c","renderDistanceChunks")).intValue());
                    Object renderer=get(mc,"field_71438_f","renderGlobal");
                    state.addProperty("render_debug",String.valueOf(method(renderer.getClass(),new String[]{"func_72735_c","getDebugInfoRenders"}).invoke(renderer)));
                    if(world!=null){Object provider=method(world.getClass(),new String[]{"func_72863_F","getChunkProvider"}).invoke(world);
                        state.addProperty("chunk_debug",String.valueOf(method(provider.getClass(),new String[]{"func_73148_d","makeString"}).invoke(provider)));}
                    telemetryError="";
                }catch(Throwable ex){telemetryError=ex.toString();}
                state.addProperty("telemetry_error",telemetryError);
                try{JsonObject target=targetBlock();if(target!=null)state.add("target_block",target);}catch(Exception ignored){}
                state.addProperty("width",((Number)get(mc,"field_71443_c","displayWidth")).intValue());
                state.addProperty("height",((Number)get(mc,"field_71440_d","displayHeight")).intValue());
                state.addProperty("input_isolated",VirtualInput.ready());
                state.addProperty("physical_events_blocked",VirtualInput.blocked.get());
                Class<?> glfw=cls("org.lwjgl.glfw.GLFW");
                long window=((Number)cls("org.lwjglx.opengl.Display").getMethod("getWindow").invoke(null)).longValue();
                state.addProperty("physical_focused",((Number)glfw.getMethod("glfwGetWindowAttrib",long.class,int.class).invoke(null,window,0x20001)).intValue()!=0);
                state.addProperty("window_visible",((Number)glfw.getMethod("glfwGetWindowAttrib",long.class,int.class).invoke(null,window,0x20004)).intValue()!=0);
                state.addProperty("cursor_free",((Number)glfw.getMethod("glfwGetInputMode",long.class,int.class).invoke(null,window,0x33001)).intValue()==0x34001);
                if(player!=null){
                    for(String[] pair:new String[][]{{"x","field_70165_t"},{"y","field_70163_u"},{"z","field_70161_v"},{"yaw","field_70177_z"},{"pitch","field_70125_A"}})
                        state.addProperty(pair[0],(Number)get(player,pair[1]));
                    state.addProperty("health",(Number)method(player.getClass(),new String[]{"func_110143_aJ","getHealth"}).invoke(player));
                    state.addProperty("player",String.valueOf(method(player.getClass(),new String[]{"func_70005_c_","getCommandSenderName"}).invoke(player)));
                    state.addProperty("dimension",((Number)get(player,"field_71093_bK","dimension")).intValue());
                    try{state.add("inventory",inventorySnapshot(player));}
                    catch(Throwable inventoryError){state.addProperty("inventory_error",inventoryError.toString());}
                }
                json("state.json",state);
            }
        }catch(Throwable ex){try{finishMining("bridge error",true);apply(new HashSet<Integer>());action=null;}catch(Exception ignored){}report(ex);}
    }
    private boolean leaseValid(long epoch,long now){
        try{
            JsonObject s=gson.fromJson(new String(Files.readAllBytes(root.resolve("safety.json")),"UTF-8"),JsonObject.class);
            long age=now-s.get("timestamp").getAsLong();
            return age>=-1000&&age<1500&&s.get("epoch").getAsLong()==epoch;
        }catch(Exception ex){return false;}
    }
    private JsonObject targetBlock()throws Exception{
        Object world=get(mc,"field_71441_e","theWorld"),hit=get(mc,"field_71476_x","objectMouseOver");
        if(world==null||hit==null||!"BLOCK".equals(String.valueOf(get(hit,"field_72313_a","typeOfHit"))))return null;
        int x=((Number)get(hit,"field_72311_b","blockX")).intValue(),y=((Number)get(hit,"field_72312_c","blockY")).intValue(),z=((Number)get(hit,"field_72309_d","blockZ")).intValue();
        Object block=method(world.getClass(),new String[]{"func_147439_a","getBlock"},int.class,int.class,int.class).invoke(world,x,y,z);
        Object registry=field(cls("net.minecraft.block.Block"),"field_149771_c","blockRegistry").get(null);
        String name=String.valueOf(method(registry.getClass(),new String[]{"func_148750_c","getNameForObject"},Object.class).invoke(registry,block));
        if("minecraft:air".equals(name))return null;
        JsonObject result=new JsonObject();result.addProperty("x",x);result.addProperty("y",y);result.addProperty("z",z);result.addProperty("block",name);
        result.addProperty("meta",(Number)method(world.getClass(),new String[]{"func_72805_g","getBlockMetadata"},int.class,int.class,int.class).invoke(world,x,y,z));
        Object player=get(mc,"field_71439_g","thePlayer");
        if(player!=null){Object inventory=get(player,"field_71071_by","inventory");result.addProperty("selected_slot",(Number)get(inventory,"field_70461_c","currentItem"));}
        return result;
    }
    private boolean canSustain()throws Exception{
        if(actionEpoch<0||!leaseValid(actionEpoch,System.currentTimeMillis())||packetTarget==null||!packetTarget.equals(targetBlock()))return false;
        if(!action.has("sustain_mining")||!action.get("sustain_mining").getAsBoolean()||get(mc,"field_71462_r","currentScreen")!=null)return false;
        JsonArray steps=action.getAsJsonArray("steps");if(steps.size()!=6)return false;
        for(JsonElement step:steps){boolean left=false;for(JsonElement k:step.getAsJsonArray()){
            String name=k.getAsString();if("LB".equals(name))left=true;if("RB".equals(name)||"MB".equals(name))return false;
        }if(!left)return false;}
        return true;
    }
    private void complete(long now,boolean cancelled)throws Exception{
        JsonObject done=new JsonObject();done.addProperty("id",lastId);done.addProperty("time",now);done.addProperty("cancelled",cancelled);
        done.addProperty("mining_continues",miningTarget!=null);json("completed.json",done);
    }
    private void finishMining(String reason,boolean release)throws Exception{
        if(miningTarget!=null){
            JsonObject done=new JsonObject();done.add("target",miningTarget);done.addProperty("started",miningStarted);
            done.addProperty("ended",System.currentTimeMillis());done.addProperty("reason",reason);json("mining-result.json",done);
            miningTarget=null;miningStop=reason;
        }
        if(release)apply(new HashSet<Integer>());
    }
    private int key(String k){
        if(k.length()==1&&k.charAt(0)>='A'&&k.charAt(0)<='Z'){
            String letters="QWERTYUIOPASDFGHJKLZXCVBNM";int[] codes={16,17,18,19,20,21,22,23,24,25,30,31,32,33,34,35,36,37,38,44,45,46,47,48,49,50};
            return codes[letters.indexOf(k)];
        }
        String[] names={"zero","one","two","three","four","five","six","seven","eight","nine","Space","Shift","Ctrl","Alt","Tab","Esc","Enter","Back","Up","Down","Left","Right","LB","RB","MB"};
        int[] codes={11,2,3,4,5,6,7,8,9,10,57,42,29,56,15,1,28,14,200,208,203,205,-100,-99,-98};
        for(int i=0;i<names.length;i++)if(names[i].equals(k))return codes[i];return 0;
    }
    private JsonArray inventorySnapshot(Object player)throws Exception{
        Object inventory=get(player,"field_71071_by","inventory");
        int size=((Number)method(inventory.getClass(),new String[]{"func_70302_i_","getSizeInventory"}).invoke(inventory)).intValue();
        Method slot=method(inventory.getClass(),new String[]{"func_70301_a","getStackInSlot"},int.class);
        Object registry=field(cls("net.minecraft.item.Item"),"field_150901_e","itemRegistry").get(null);
        JsonArray result=new JsonArray();
        for(int i=0;i<Math.min(size,200);i++){
            Object stack=slot.invoke(inventory,i);if(stack==null)continue;
            int count=((Number)get(stack,"field_77994_a","stackSize")).intValue();if(count<=0)continue;
            Object item=method(stack.getClass(),new String[]{"func_77973_b","getItem"}).invoke(stack);
            String id=String.valueOf(method(registry.getClass(),new String[]{"func_148750_c","getNameForObject"},Object.class).invoke(registry,item));
            String name=id;try{name=String.valueOf(method(stack.getClass(),new String[]{"func_82833_r","getDisplayName"}).invoke(stack));}catch(Exception ignored){}
            JsonObject entry=new JsonObject();entry.addProperty("slot",i);entry.addProperty("item",id);entry.addProperty("name",name);entry.addProperty("count",count);result.add(entry);
        }
        return result;
    }
    private void apply(Set<Integer> next)throws Exception{
        VirtualInput.setKeys(next);
        VirtualInput.begin();
        try {applyVirtual(next);} finally {VirtualInput.end();}
    }
    private void applyVirtual(Set<Integer> next)throws Exception{
        Object screen=get(mc,"field_71462_r","currentScreen");
        Class<?> mouseClass=cls("org.lwjglx.input.Mouse");
        Method mouseEvent=mouseClass.getMethod("addButtonEvent",int.class,boolean.class);
        for(Integer n:new HashSet<Integer>(guiMouseHeld))if(!next.contains(n)){
            mouseEvent.invoke(null,n+100,false);guiMouseHeld.remove(n);
        }
        if(screen!=null){
            int w=((Number)get(mc,"field_71443_c","displayWidth")).intValue();
            int h=((Number)get(mc,"field_71440_d","displayHeight")).intValue();
            int sw=((Number)get(screen,"field_146294_l","width")).intValue();
            int sh=((Number)get(screen,"field_146295_m","height")).intValue();
            int x=cursorX*sw/w,y=cursorY*sh/h;
            for(int n:next){
                if(n<0){
                    if(!held.contains(n)){
                        mouseEvent.invoke(null,n+100,true);guiMouseHeld.add(n);
                    }
                }else if(!held.contains(n)){
                    char ch=n==18?'e':n==19?'r':n==22?'u':n==57?' ':'\0';
                    method(screen.getClass(),new String[]{"func_73869_a","keyTyped"},char.class,int.class).invoke(screen,ch,n);
                }
            }
        }
        Class<?> kb=cls("net.minecraft.client.settings.KeyBinding");
        Method set=method(kb,new String[]{"func_74510_a","setKeyBindState"},int.class,boolean.class);
        Method press=method(kb,new String[]{"func_74507_a","onTick"},int.class);
        for(int n:held)if(!next.contains(n))set.invoke(null,n,false);
        for(int n:next){set.invoke(null,n,true);if(!held.contains(n))press.invoke(null,n);}
        held=next;
    }
    /** Replays hardware callback entry points inside this client; no OS input injection. */
    private void probeInput(long id)throws Exception{
        if(!held.isEmpty())throw new IllegalStateException("Pause actions before input probe");
        Class<?> mouse=cls("org.lwjglx.input.Mouse"),keyboard=cls("org.lwjglx.input.Keyboard");
        while((Boolean)mouse.getMethod("next").invoke(null)){}
        while((Boolean)keyboard.getMethod("next").invoke(null)){}
        int beforeX=field(mouse,"latestX").getInt(null),beforeY=field(mouse,"latestY").getInt(null);
        long blocked=VirtualInput.blocked.get();
        mouse.getMethod("addMoveEvent",double.class,double.class).invoke(null,123.0,234.0);
        mouse.getMethod("addButtonEvent",int.class,boolean.class).invoke(null,0,true);
        mouse.getMethod("addWheelEvent",double.class).invoke(null,1.0);
        keyboard.getMethod("addGlfwKeyEvent",long.class,int.class,int.class,int.class,int.class,int.class).invoke(null,0L,65,0,1,0,97);
        keyboard.getMethod("addCharEvent",int.class,int.class).invoke(null,0,97);
        JsonObject result=new JsonObject();result.addProperty("id",id);
        result.addProperty("timestamp",System.currentTimeMillis());
        result.addProperty("physical_mouse_queue_empty",!(Boolean)mouse.getMethod("next").invoke(null));
        result.addProperty("physical_keyboard_queue_empty",!(Boolean)keyboard.getMethod("next").invoke(null));
        result.addProperty("physical_cursor_unchanged",beforeX==field(mouse,"latestX").getInt(null)&&beforeY==field(mouse,"latestY").getInt(null));
        result.addProperty("blocked_callback_count",VirtualInput.blocked.get()-blocked);
        Set<Integer> testKeys=new HashSet<Integer>(Arrays.asList(17,-100));
        VirtualInput.setKeys(testKeys);
        try{
            result.addProperty("virtual_W_poll",(Boolean)keyboard.getMethod("isKeyDown",int.class).invoke(null,17));
            result.addProperty("virtual_LB_poll",(Boolean)mouse.getMethod("isButtonDown",int.class).invoke(null,0));
            VirtualInput.begin();
            try{mouse.getMethod("addButtonEvent",int.class,boolean.class).invoke(null,0,true);}finally{VirtualInput.end();}
            boolean present=(Boolean)mouse.getMethod("next").invoke(null);
            result.addProperty("virtual_click_received",present&&(Integer)mouse.getMethod("getEventButton").invoke(null)==0&&(Boolean)mouse.getMethod("getEventButtonState").invoke(null));
        }finally{VirtualInput.setKeys(held);}
        result.addProperty("released_W_poll",!(Boolean)keyboard.getMethod("isKeyDown",int.class).invoke(null,17));
        result.addProperty("released_LB_poll",!(Boolean)mouse.getMethod("isButtonDown",int.class).invoke(null,0));
        json("input-probe-result.json",result);
    }
    @SubscribeEvent public void render(TickEvent.RenderTickEvent e){
        if(mc==null||e.phase!=TickEvent.Phase.END)return;
        try{
            long now=System.currentTimeMillis();
            renderedFrames++;
            if(now-fpsSince>=1000){renderFps=renderedFrames*1000.0/(now-fpsSince);renderedFrames=0;fpsSince=now;}
            if(action!=null){
                long elapsed=now-started;int step=(int)(elapsed/33.333333);
                if(step>=6){
                    if(canSustain()){
                        miningTarget=packetTarget;miningEpoch=actionEpoch;miningStarted=now;miningDeadline=now+10000;miningStop="";
                        apply(new HashSet<Integer>(Arrays.asList(-100)));
                    }else apply(new HashSet<Integer>());
                    complete(now,false);action=null;
                }
                else{Set<Integer> next=new HashSet<Integer>();JsonArray steps=action.getAsJsonArray("steps");
                    if(step<steps.size())for(JsonElement k:steps.get(step).getAsJsonArray()){int n=key(k.getAsString());if(n!=0)next.add(n);}
                    apply(next);
                }
            }
            if(now-lastFrame>1000){
                lastFrame=now;int w=((Number)get(mc,"field_71443_c","displayWidth")).intValue(),h=((Number)get(mc,"field_71440_d","displayHeight")).intValue();
                if(w<=0||h<=0||w*h>4000000)return;
                ByteBuffer pixels=ByteBuffer.allocateDirect(w*h*4);
                Class<?> gl=cls("org.lwjgl.opengl.GL11");
                gl.getMethod("glReadPixels",int.class,int.class,int.class,int.class,int.class,int.class,ByteBuffer.class).invoke(null,0,0,w,h,6408,5121,pixels);
                BufferedImage image=new BufferedImage(w,h,BufferedImage.TYPE_INT_RGB);
                for(int y=0;y<h;y++)for(int x=0;x<w;x++){int i=(y*w+x)*4;image.setRGB(x,h-y-1,((pixels.get(i)&255)<<16)|((pixels.get(i+1)&255)<<8)|(pixels.get(i+2)&255));}
                if(get(mc,"field_71462_r","currentScreen")!=null){
                    java.awt.Graphics2D g=image.createGraphics();g.setColor(java.awt.Color.YELLOW);
                    g.drawLine(cursorX-5,cursorY,cursorX+5,cursorY);g.drawLine(cursorX,cursorY-5,cursorX,cursorY+5);g.dispose();
                }
                Path tmp=root.resolve("frame.tmp.jpg");ImageIO.write(image,"jpg",tmp.toFile());Files.move(tmp,root.resolve("frame.jpg"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
            }
        }catch(Throwable ex){try{finishMining("render error",true);apply(new HashSet<Integer>());action=null;}catch(Exception ignored){}report(ex);}
    }
}
