function onResponse() {
    document.body.innerHTML = this.responseText;
}

// This would work if I had modern JS :(
/*
async function buttonClick() {
    const url = "http://192.168.1.11:8080/dashboard/";
    const result = await fetch(url)
        .then(response => response.text())
        .catch(error => { return });

    document.body.innerHTML = result;
}
*/

function buttonClick() {
    var req = new XMLHttpRequest();
    req.addEventListener("load", onResponse);
    req.open("GET", "http://192.168.1.11:8080/dashboard/");
    req.send();
}

if(typeof intId === 'undefined') {
	var intId = setInterval(buttonClick, 60000);
}
