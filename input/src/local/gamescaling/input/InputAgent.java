// SPDX-License-Identifier: GPL-3.0-or-later
package local.gamescaling.input;

import java.lang.instrument.*;
import java.security.ProtectionDomain;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import gsinput.VirtualInput;

/** Input isolation for the copied lwjgl3ify 2.1.16 client, never the desktop. */
public final class InputAgent implements ClassFileTransformer, Opcodes {
    private static final String STATE = "gsinput/VirtualInput";
    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new InputAgent());
        System.out.println("[GameScaling input] isolated client input enabled");
    }
    private static InsnList call(String name, String desc) {
        InsnList out = new InsnList();
        out.add(new MethodInsnNode(INVOKESTATIC, STATE, name, desc, false));
        return out;
    }
    private static void replace(MethodNode m, InsnList code) {
        m.instructions.clear(); m.tryCatchBlocks.clear();
        if (m.localVariables != null) m.localVariables.clear();
        m.instructions.add(code);
    }
    private static void guard(MethodNode m) {
        InsnList code = call("acceptEvent", "()Z");
        LabelNode accepted = new LabelNode();
        code.add(new JumpInsnNode(IFNE, accepted)); code.add(new InsnNode(RETURN));
        code.add(accepted); code.add(new FrameNode(F_SAME, 0, null, 0, null));
        m.instructions.insert(code);
    }
    public byte[] transform(ClassLoader loader, String name, Class<?> type,
                            ProtectionDomain domain, byte[] bytes) {
        boolean mouse = "org/lwjglx/input/Mouse".equals(name);
        boolean keyboard = "org/lwjglx/input/Keyboard".equals(name);
        boolean display = "org/lwjglx/opengl/Display".equals(name);
        if (!mouse && !keyboard && !display) return null;
        try {
            ClassNode c = new ClassNode(); new ClassReader(bytes).accept(c, 0);
            int edits = 0;
            for (MethodNode m : c.methods) {
                if (mouse && ((m.name.equals("addMoveEvent") && m.desc.equals("(DD)V"))
                        || (m.name.equals("addButtonEvent") && m.desc.equals("(IZ)V"))
                        || (m.name.equals("addWheelEvent") && m.desc.equals("(D)V")))) {
                    guard(m); edits++;
                } else if (keyboard && (m.name.equals("addGlfwKeyEvent")
                        || m.name.equals("addCharEvent") || m.name.equals("addRawKeyEvent"))) {
                    guard(m); edits++;
                } else if ((mouse && m.name.equals("isButtonDown") && m.desc.equals("(I)Z"))
                        || (keyboard && m.name.equals("isKeyDown") && m.desc.equals("(I)Z"))) {
                    InsnList code = new InsnList(); code.add(new VarInsnNode(ILOAD, 0));
                    code.add(call(mouse ? "buttonDown" : "keyDown", "(I)Z"));
                    code.add(new InsnNode(IRETURN)); replace(m, code); edits++;
                } else if (mouse && m.name.equals("setGrabbed") && m.desc.equals("(Z)V")) {
                    // Keep Minecraft's logical grab state, but never capture the OS pointer.
                    InsnList code = new InsnList(); code.add(new VarInsnNode(ILOAD, 0));
                    code.add(new FieldInsnNode(PUTSTATIC, name, "grabbed", "Z"));
                    code.add(new InsnNode(RETURN)); replace(m, code); edits++;
                } else if (mouse && m.name.equals("setCursorPosition") && m.desc.equals("(II)V")) {
                    InsnList code = new InsnList();
                    for (String f : new String[]{"x", "latestX", "y", "latestY"}) {
                        code.add(new VarInsnNode(ILOAD, f.endsWith("X") || f.equals("x") ? 0 : 1));
                        code.add(new FieldInsnNode(PUTSTATIC, name, f, "I"));
                    }
                    code.add(new InsnNode(RETURN)); replace(m, code); edits++;
                } else if (mouse && (m.name.equals("getDX") || m.name.equals("getDY")) && m.desc.equals("()I")) {
                    InsnList code = new InsnList(); code.add(new InsnNode(ICONST_0));
                    code.add(new InsnNode(IRETURN)); replace(m, code); edits++;
                } else if (display && (m.name.equals("isActive") || m.name.equals("isVisible")) && m.desc.equals("()Z")) {
                    // Focus/visibility are virtual for game scheduling, not for the compositor.
                    InsnList code = new InsnList(); code.add(new InsnNode(ICONST_1));
                    code.add(new InsnNode(IRETURN)); replace(m, code); edits++;
                } else if (display && m.name.equals("create")) {
                    for (AbstractInsnNode node : m.instructions.toArray()) {
                        if (node instanceof MethodInsnNode && ((MethodInsnNode)node).owner.equals("org/lwjgl/glfw/GLFW")
                                && ((MethodInsnNode)node).name.equals("glfwCreateWindow")) {
                            InsnList hints = new InsnList();
                            // Unfocused, no focus-on-show, and no desktop window; keep GL context.
                            for (int hint : new int[]{0x20001, 0x2000C, 0x20004}) {
                                hints.add(new LdcInsnNode(hint)); hints.add(new InsnNode(ICONST_0));
                                hints.add(new MethodInsnNode(INVOKESTATIC, "org/lwjgl/glfw/GLFW", "glfwWindowHint", "(II)V", false));
                            }
                            m.instructions.insertBefore(node, hints); edits++;
                        }
                    }
                }
            }
            int expected = mouse ? 8 : keyboard ? 4 : 3;
            if (edits != expected) throw new IllegalStateException("Expected " + expected + " hooks, found " + edits);
            ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
            c.accept(writer);
            byte[] result = writer.toByteArray(); VirtualInput.patched.add(name);
            System.out.println("[GameScaling input] patched " + name + " (" + edits + " hooks)");
            return result;
        } catch (Throwable ex) {
            ex.printStackTrace();
            // Fail this dedicated test process rather than silently running without isolation.
            Runtime.getRuntime().halt(70); return null;
        }
    }
}
