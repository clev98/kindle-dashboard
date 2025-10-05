function onResponse() {
    document.body.innerHTML = this.responseText;
}

function buttonClick() {
    var req = new XMLHttpRequest();

    req.addEventListener("load", onResponse);
    req.open("GET", "http://192.168.1.11:8080/dashboard/");
    req.send();
}

if(typeof intId === 'undefined') {
	var intId = setInterval(buttonClick, 60000);
}
