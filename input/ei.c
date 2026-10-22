/* Input sender for the project's PRIVATE KWin bus. No default/session bus fallback. */
#include <libei.h>
#include <dbus/dbus.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <time.h>
static struct ei *context;
static struct ei_device *keyboard,*pointer,*absolute,*buttons,*scrolling;
static DBusConnection *connection;
static uint64_t now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
void gs_pump(void){
 if(!context)return;ei_dispatch(context);struct ei_event *event;
 while((event=ei_get_event(context))){
  enum ei_event_type type=ei_event_get_type(event);struct ei_device *device=ei_event_get_device(event);
  if(type==EI_EVENT_SEAT_ADDED){struct ei_seat *seat=ei_event_get_seat(event);ei_seat_bind_capabilities(seat,EI_DEVICE_CAP_POINTER,EI_DEVICE_CAP_POINTER_ABSOLUTE,EI_DEVICE_CAP_KEYBOARD,EI_DEVICE_CAP_BUTTON,EI_DEVICE_CAP_SCROLL,NULL);}
  if(type==EI_EVENT_DEVICE_RESUMED){
   ei_device_start_emulating(device,1);
   fprintf(stderr,"[private input] device %s pointer=%d keyboard=%d buttons=%d\n",ei_device_get_name(device),ei_device_has_capability(device,EI_DEVICE_CAP_POINTER),ei_device_has_capability(device,EI_DEVICE_CAP_KEYBOARD),ei_device_has_capability(device,EI_DEVICE_CAP_BUTTON));
   if(ei_device_has_capability(device,EI_DEVICE_CAP_KEYBOARD)&&!keyboard)keyboard=ei_device_ref(device);
   if(ei_device_has_capability(device,EI_DEVICE_CAP_POINTER)&&!pointer){pointer=ei_device_ref(device);if(ei_device_has_capability(device,EI_DEVICE_CAP_BUTTON)){if(buttons)ei_device_unref(buttons);buttons=ei_device_ref(device);}}
   if(ei_device_has_capability(device,EI_DEVICE_CAP_POINTER_ABSOLUTE)&&!absolute)absolute=ei_device_ref(device);
   if(ei_device_has_capability(device,EI_DEVICE_CAP_BUTTON)&&!buttons)buttons=ei_device_ref(device);
   if(ei_device_has_capability(device,EI_DEVICE_CAP_SCROLL)&&!scrolling)scrolling=ei_device_ref(device);
  }
  if(type==EI_EVENT_DEVICE_PAUSED||type==EI_EVENT_DEVICE_REMOVED){
   if(keyboard==device){ei_device_unref(keyboard);keyboard=NULL;}if(pointer==device){ei_device_unref(pointer);pointer=NULL;}
   if(absolute==device){ei_device_unref(absolute);absolute=NULL;}
   if(buttons==device){ei_device_unref(buttons);buttons=NULL;}if(scrolling==device){ei_device_unref(scrolling);scrolling=NULL;}
  }
  ei_event_unref(event);
 }
}
int gs_connect(const char *address,int expected_pid){
 if(!address||!*address)return -1;DBusError error;dbus_error_init(&error);
 connection=dbus_connection_open_private(address,&error);
 if(!connection||!dbus_bus_register(connection,&error)){fprintf(stderr,"Private DBus: %s\n",error.message?error.message:"failed");return -2;}
 DBusMessage *check=dbus_message_new_method_call(DBUS_SERVICE_DBUS,DBUS_PATH_DBUS,DBUS_INTERFACE_DBUS,"GetConnectionUnixProcessID");
 const char *owner="org.kde.KWin";dbus_message_append_args(check,DBUS_TYPE_STRING,&owner,DBUS_TYPE_INVALID);
 DBusMessage *checked=dbus_connection_send_with_reply_and_block(connection,check,5000,&error);dbus_message_unref(check);
 uint32_t compositor_pid=0;
 if(!checked||!dbus_message_get_args(checked,&error,DBUS_TYPE_UINT32,&compositor_pid,DBUS_TYPE_INVALID)||compositor_pid!=(uint32_t)expected_pid){if(checked)dbus_message_unref(checked);return -7;}
 dbus_message_unref(checked);
 DBusMessage *request=dbus_message_new_method_call("org.kde.KWin","/org/kde/KWin/EIS/RemoteDesktop","org.kde.KWin.EIS.RemoteDesktop","connectToEIS");
 int32_t caps=3;dbus_message_append_args(request,DBUS_TYPE_INT32,&caps,DBUS_TYPE_INVALID);
 DBusMessage *reply=dbus_connection_send_with_reply_and_block(connection,request,5000,&error);dbus_message_unref(request);
 if(!reply){fprintf(stderr,"Private EIS: %s\n",error.message?error.message:"failed");return -3;}
 int fd=-1;int32_t cookie=0;
 if(!dbus_message_get_args(reply,&error,DBUS_TYPE_UNIX_FD,&fd,DBUS_TYPE_INT32,&cookie,DBUS_TYPE_INVALID)){dbus_message_unref(reply);return -4;}
 fd=dup(fd);dbus_message_unref(reply);context=ei_new_sender(NULL);ei_configure_name(context,"GameScaling private Minecraft session");
 if(ei_setup_backend_fd(context,fd)<0)return -5;
 for(int i=0;i<300;i++){gs_pump();if(keyboard&&pointer&&buttons)return 0;usleep(10000);}return -6;
}
int gs_ready(void){gs_pump();return !!keyboard&&!!pointer&&!!buttons;}
void gs_key(int code,int down){gs_pump();if(keyboard){ei_device_keyboard_key(keyboard,code,down);ei_device_frame(keyboard,now_us());}}
void gs_button(int code,int down){gs_pump();if(buttons){ei_device_button_button(buttons,code,down);ei_device_frame(buttons,now_us());}}
void gs_motion(double dx,double dy){gs_pump();if(pointer){ei_device_pointer_motion(pointer,dx,dy);ei_device_frame(pointer,now_us());}}
void gs_scroll(int delta){gs_pump();if(scrolling){ei_device_scroll_discrete(scrolling,0,-120*delta);ei_device_frame(scrolling,now_us());}}

void gs_absolute(double x,double y){gs_pump();if(absolute){ei_device_pointer_motion_absolute(absolute,x,y);ei_device_frame(absolute,now_us());}}
