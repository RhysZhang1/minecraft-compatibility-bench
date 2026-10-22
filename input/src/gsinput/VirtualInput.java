package gsinput;

import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

/** One process-local state, loaded by the bootstrap loader, shared across Forge/RFB. */
public final class VirtualInput {
    private static final ThreadLocal<Boolean> virtual = new ThreadLocal<Boolean>();
    private static volatile Set<Integer> keys = Collections.emptySet();
    public static final AtomicLong blocked = new AtomicLong();
    public static final Set<String> patched = Collections.synchronizedSet(new HashSet<String>());
    public static void begin() { virtual.set(Boolean.TRUE); }
    public static void end() { virtual.remove(); }
    public static boolean acceptEvent() {
        if (Boolean.TRUE.equals(virtual.get())) return true;
        blocked.incrementAndGet();
        return false;
    }
    public static void setKeys(Set<Integer> next) {
        keys = Collections.unmodifiableSet(new HashSet<Integer>(next));
    }
    public static boolean keyDown(int code) { return keys.contains(code); }
    public static boolean buttonDown(int button) { return keys.contains(button - 100); }
    public static boolean ready() {
        return patched.contains("org/lwjglx/input/Mouse")
            && patched.contains("org/lwjglx/input/Keyboard")
            && patched.contains("org/lwjglx/opengl/Display");
    }
}
