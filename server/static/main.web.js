async function buttonClick() {
    const url = "http://192.168.1.11:8080/dashboard/";
    const response = await fetch(url);

    if (!response.ok) {
        return;
    }

    const result = await response.text();

    document.body.innerHTML = result;
}

if(typeof intId === 'undefined') {
	var intId = setInterval(buttonClick, 60000);
}
