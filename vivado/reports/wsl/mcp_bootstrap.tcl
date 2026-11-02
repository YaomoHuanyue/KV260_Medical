puts "BOOT_TOOL=[version -short]"
if {![llength [info commands webserver]]} {error "ROSS_WEBSERVER_COMMAND_UNAVAILABLE"}
webserver -start -port 19088 -key none
puts "ROSS_WEBSERVER_READY"
set _owned_keepalive 0
vwait _owned_keepalive
