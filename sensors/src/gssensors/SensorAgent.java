// SPDX-License-Identifier: GPL-3.0-or-later
package gssensors;
import java.lang.instrument.*;
import java.security.ProtectionDomain;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Version mappings select the target; unchanged input code supports other loaders. */
public final class SensorAgent implements ClassFileTransformer,Opcodes {
    public static void premain(String args,Instrumentation inst){inst.addTransformer(new SensorAgent());}
    public byte[] transform(ClassLoader loader,String name,Class<?> type,ProtectionDomain domain,byte[] bytes){
        if(!name.equals(Sensors.className("net.minecraft.client.Minecraft").replace('.','/')))return null;
        try{
            Sensors.loader=loader;ClassNode c=new ClassNode();new ClassReader(bytes).accept(c,0);int found=0;
            String tick=Sensors.bindings.getProperty("method.net.minecraft.client.Minecraft.tick.0","tick");
            for(MethodNode m:c.methods)if(m.desc.equals("()V")&&java.util.Arrays.asList(tick.split(",")).contains(m.name)){
                for(AbstractInsnNode i:m.instructions.toArray())if(i.getOpcode()==RETURN)m.instructions.insertBefore(i,new MethodInsnNode(INVOKESTATIC,"gssensors/Sensors","tick","()V",false));found++;
            }
            if(found!=1)throw new IllegalStateException("Expected one tick method, got "+found);
            ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(writer);System.out.println("[GameScaling sensors] read-only telemetry attached to "+name);return writer.toByteArray();
        }catch(Throwable e){e.printStackTrace();return null;}
    }
}
