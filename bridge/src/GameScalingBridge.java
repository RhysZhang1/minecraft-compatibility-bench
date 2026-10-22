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

/** Client-local actions only: this mod never injects operating-system input. */
@Mod(modid="gamescalingbridge",name="GameScaling local bridge",version="1.0",acceptableRemoteVersions="*")
public class GameScalingBridge {
    private final Path root=Paths.get(System.getProperty("gamescaling.bridge","gamescaling-bridge"));
    private final Gson gson=new Gson();
    private long lastFrame=0,lastStatus=0,lastConnect=0,started=0,lastId=-1;
    private JsonObject action=null;
    private String error="";
    private Object mc;
    private Set<Integer> held=new HashSet<Integer>();
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
            Files.createDirectories(root);
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
            if(world==null&&screen!=null&&screen.getClass().getSimpleName().equals("GuiMainMenu")&&now-lastConnect>15000){
                lastConnect=now;
                Class<?> gs=cls("net.minecraft.client.gui.GuiScreen"),sd=cls("net.minecraft.client.multiplayer.ServerData");
                Object data=sd.getConstructor(String.class,String.class).newInstance("GTNH local test","127.0.0.1:25565");
                Object gui=cls("net.minecraft.client.multiplayer.GuiConnecting").getConstructor(gs,mc.getClass(),sd).newInstance(screen,mc,data);
                method(mc.getClass(),new String[]{"func_147108_a","displayGuiScreen"},gs).invoke(mc,gui);
            }
            Object player=get(mc,"field_71439_g","thePlayer");
            if(player!=null){
                if(((Number)get(player,"field_70725_aQ","deathTime")).intValue()>20)
                    method(player.getClass(),new String[]{"func_71004_bE","respawnPlayer"}).invoke(player);
            }
            Path command=root.resolve("command.json");
            if(Files.exists(command)){
                JsonObject a=gson.fromJson(new String(Files.readAllBytes(command),"UTF-8"),JsonObject.class);
                long id=a.get("id").getAsLong();
                if(id>lastId&&action==null){
                    lastId=id;action=a;started=now;
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
                    }
                }
            }
            if(now-lastStatus>500){lastStatus=now;JsonObject state=new JsonObject();
                state.addProperty("timestamp",now);state.addProperty("connected",world!=null&&player!=null);
                state.addProperty("screen",screen==null?"":screen.getClass().getSimpleName());
                state.addProperty("command_id",lastId);state.addProperty("busy",action!=null);state.addProperty("error",error);
                if(player!=null){
                    for(String[] pair:new String[][]{{"x","field_70165_t"},{"y","field_70163_u"},{"z","field_70161_v"},{"yaw","field_70177_z"},{"pitch","field_70125_A"}})
                        state.addProperty(pair[0],(Number)get(player,pair[1]));
                    state.addProperty("health",(Number)method(player.getClass(),new String[]{"func_110143_aJ","getHealth"}).invoke(player));
                }
                json("state.json",state);
            }
        }catch(Throwable ex){error=ex.toString();if(System.currentTimeMillis()-lastStatus>5000){lastStatus=System.currentTimeMillis();ex.printStackTrace();}}
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
    private void apply(Set<Integer> next)throws Exception{
        Class<?> kb=cls("net.minecraft.client.settings.KeyBinding");
        Method set=method(kb,new String[]{"func_74510_a","setKeyBindState"},int.class,boolean.class);
        Method press=method(kb,new String[]{"func_74507_a","onTick"},int.class);
        for(int n:held)if(!next.contains(n))set.invoke(null,n,false);
        for(int n:next){set.invoke(null,n,true);if(!held.contains(n))press.invoke(null,n);}
        held=next;
    }
    @SubscribeEvent public void render(TickEvent.RenderTickEvent e){
        if(mc==null||e.phase!=TickEvent.Phase.END)return;
        try{
            long now=System.currentTimeMillis();
            if(action!=null){
                long elapsed=now-started;int step=(int)(elapsed/33.333333);
                if(step>=6){apply(new HashSet<Integer>());JsonObject done=new JsonObject();done.addProperty("id",lastId);done.addProperty("time",now);json("completed.json",done);action=null;}
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
                Path tmp=root.resolve("frame.tmp.jpg");ImageIO.write(image,"jpg",tmp.toFile());Files.move(tmp,root.resolve("frame.jpg"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
            }
        }catch(Throwable ex){error=ex.toString();}
    }
}
