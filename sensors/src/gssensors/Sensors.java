package gssensors;
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
/** Optional, read-only client telemetry. Input never depends on these names. */
public final class Sensors {
    static Properties bindings=new Properties();static ClassLoader loader;static long last;static String error="";
    static Path root=Paths.get(System.getProperty("gamescaling.bridge"));
    static {
        try {bindings.load(Files.newInputStream(Paths.get(System.getProperty("gamescaling.bindings"))));}catch(Exception e){throw new RuntimeException(e);}
    }
    static String className(String named){return bindings.getProperty("class."+named,named);}
    static Class<?> cls(String named)throws Exception{return Class.forName(className(named),false,loader);}
    static String names(Class<?> c,String kind,String name){
        String named=bindings.getProperty("reverse."+c.getName(),c.getName());return bindings.getProperty(kind+"."+named+"."+name,name);
    }
    static Object get(Object obj,String name)throws Exception{
        for(Class<?> c=obj.getClass();c!=null;c=c.getSuperclass())for(String n:names(c,"field",name).split(","))try{Field f=c.getDeclaredField(n);f.setAccessible(true);return f.get(obj);}catch(NoSuchFieldException ignored){}
        throw new NoSuchFieldException(name);
    }
    static Object call(Object obj,String name,Object...args)throws Exception{
        Class<?> type=obj instanceof Class?(Class<?>)obj:obj.getClass();
        for(Class<?> c:hierarchy(type)){
            String named=bindings.getProperty("reverse."+c.getName(),c.getName());
            String spec=bindings.getProperty("signature."+named+"."+name+"."+args.length);
            for(Method m:c.getDeclaredMethods()){
                if(m.getParameterTypes().length!=args.length)continue;boolean match=false;
                if(spec==null)match=m.getName().equals(name);
                else for(String entry:spec.split(";")){
                    String[] parts=entry.split("\\|",-1);
                    if(m.getName().equals(parts[0])&&m.getReturnType().getName().equals(className(parts[1])))match=true;
                }
                if(!match)continue;
                try{m.setAccessible(true);return m.invoke(obj instanceof Class?null:obj,args);}catch(IllegalArgumentException ignored){}
            }
        }
        throw new NoSuchMethodException(type.getName()+"."+name);
    }
    static Set<Class<?>> hierarchy(Class<?> type){Set<Class<?>> result=new LinkedHashSet<Class<?>>();if(type!=null){result.add(type);result.addAll(hierarchy(type.getSuperclass()));for(Class<?> i:type.getInterfaces())result.addAll(hierarchy(i));}return result;}
    static Map<String,Object> map(){return new LinkedHashMap<String,Object>();}
    static Object registry(String type,Object item)throws Exception{
        try{
            Object registry=cls("net.minecraft.core.registries.BuiltInRegistries").getField(bindings.getProperty("field.net.minecraft.core.registries.BuiltInRegistries."+type,type)).get(null);
            return call(registry,"getKey",item).toString();
        }catch(ClassNotFoundException e){
            String name=type.equals("ITEM")?"net.minecraft.item.Item":"net.minecraft.block.Block";
            Class<?> c=cls(name);String logical=type.equals("ITEM")?"itemRegistry":"blockRegistry";
            Field field=c.getDeclaredField(bindings.getProperty("field."+name+"."+logical));field.setAccessible(true);
            return call(field.get(null),"getNameForObject",item).toString();
        }
    }
    static Object value(Object object,String method,String field)throws Exception{
        try{return call(object,method);}catch(NoSuchMethodException e){return get(object,field);}
    }
    public static void tick(){
        long now=System.currentTimeMillis();if(now-last<50)return;last=now;
        Map<String,Object> out=map();out.put("timestamp",now);out.put("session",System.getProperty("gamescaling.session"));
        try {
            Object mc=call(cls("net.minecraft.client.Minecraft"),"getInstance");Object player=get(mc,"player");out.put("world_loaded",player!=null&&get(mc,"level")!=null);
            try{Object mouse=get(mc,"mouseHandler");out.put("mouse_left_pressed",call(mouse,"isLeftPressed"));out.put("mouse_grabbed",call(mouse,"isMouseGrabbed"));}catch(Exception ignored){}
            Object screen;try{screen=get(mc,"screen");}catch(NoSuchFieldException e){screen=call(get(mc,"gui"),"screen");}out.put("screen",screen==null?"":bindings.getProperty("reverse."+screen.getClass().getName(),screen.getClass().getSimpleName()));
            if(player!=null){
                for(String axis:new String[]{"X","Y","Z"})out.put(axis.toLowerCase(),value(player,"get"+axis,"pos"+axis));
                try{out.put("y",((Number)out.get("y")).doubleValue()-((Number)get(player,"yOffset")).doubleValue());}catch(NoSuchFieldException ignored){}
                out.put("feet_y",out.get("y"));out.put("yaw",value(player,"getYRot","rotationYaw"));out.put("pitch",value(player,"getXRot","rotationPitch"));out.put("health",call(player,"getHealth"));out.put("on_ground",value(player,"onGround","onGround"));
                out.put("player",System.getProperty("gamescaling.player","GameScalingBot"));
                try {
                    Object inv=value(player,"getInventory","inventory");int size=((Number)call(inv,"getContainerSize")).intValue();List<Object> items=new ArrayList<Object>();
                    for(int i=0;i<size;i++){Object stack=call(inv,"getItem",i);if(stack==null)continue;try{if(Boolean.TRUE.equals(call(stack,"isEmpty")))continue;}catch(NoSuchMethodException ignored){}
                        Map<String,Object> item=map();item.put("slot",i);item.put("count",value(stack,"getCount","count"));item.put("item",registry("ITEM",call(stack,"getItem")));Object label;try{label=call(stack,"getHoverName");}catch(NoSuchMethodException e){label=call(stack,"getDisplayName");}item.put("name",label instanceof String?label:call(label,"getString"));items.add(item);}
                    out.put("inventory",items);try{out.put("selected_slot",call(inv,"getSelectedSlot"));}catch(Exception e){out.put("selected_slot",get(inv,"selected"));}
                }catch(Exception e){out.put("inventory_error",e.toString());e.printStackTrace();}
                try{
                    Object hit=get(mc,"hitResult");if(hit!=null&&value(hit,"getType","typeOfHit").toString().equals("BLOCK")){
                        Map<String,Object> target=map();Object block;
                        try{
                            Object pos=call(hit,"getBlockPos");for(String axis:new String[]{"X","Y","Z"})target.put(axis.toLowerCase(),call(pos,"get"+axis));
                            block=call(call(get(mc,"level"),"getBlockState",pos),"getBlock");
                        }catch(NoSuchMethodException e){
                            for(String axis:new String[]{"x","y","z"})target.put(axis,get(hit,axis));
                            block=call(get(mc,"level"),"getBlock",target.get("x"),target.get("y"),target.get("z"));
                        }
                        target.put("block",registry("BLOCK",block));out.put("target_block",target);
                    }
                }catch(Exception e){out.put("target_error",e.toString());}
            }
            try{out.put("render_fps",value(mc,"getFps","debugFPS"));}catch(Exception ignored){}
            if(screen!=null)try{out.put("gui_width",get(screen,"width"));out.put("gui_height",get(screen,"height"));}catch(Exception ignored){}
            out.put("telemetry_ready",true);
        }catch(Throwable e){out.put("telemetry_error",e.toString());if(!e.toString().equals(error)){error=e.toString();e.printStackTrace();}}
        try{Path tmp=root.resolve("sensors.json.tmp");Files.write(tmp,json(out).getBytes("UTF-8"));Files.move(tmp,root.resolve("sensors.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}catch(Exception e){e.printStackTrace();}
    }
    static String json(Object value){
        if(value==null)return "null";if(value instanceof Number||value instanceof Boolean)return value.toString();
        if(value instanceof Map){StringBuilder s=new StringBuilder("{");for(Object k:((Map<?,?>)value).keySet()){if(s.length()>1)s.append(',');s.append(json(k)).append(':').append(json(((Map<?,?>)value).get(k)));}return s.append('}').toString();}
        if(value instanceof Iterable){StringBuilder s=new StringBuilder("[");for(Object x:(Iterable<?>)value){if(s.length()>1)s.append(',');s.append(json(x));}return s.append(']').toString();}
        StringBuilder s=new StringBuilder("\"");for(char c:value.toString().toCharArray()){if(c=='"'||c=='\\')s.append('\\').append(c);else if(c<32)s.append(String.format("\\u%04x",(int)c));else s.append(c);}return s.append('"').toString();
    }
}
