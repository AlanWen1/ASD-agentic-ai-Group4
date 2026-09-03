const TOKEN_KEY = "finance_token";

function authToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
}

function captureSharedToken() {
    const url = new URL(window.location.href);
    const sharedToken = url.searchParams.get("token");

    if (sharedToken) {
        localStorage.setItem(TOKEN_KEY, sharedToken);

        url.searchParams.delete("token");

        history.replaceState(
            {},
            document.title,
            `${url.pathname}${url.search}${url.hash}`
        );
    }
}

captureSharedToken();

if (!authToken()) {
    window.location.replace("http://localhost:3000/");
}

document.body.addEventListener("htmx:configRequest", function (event) {
    const token = authToken();

    if (token) {
        event.detail.headers["Authorization"] = `Bearer ${token}`;
    }
});

document.body.addEventListener("htmx:responseError", function (event) {
    if (event.detail.xhr.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        window.location.replace("http://localhost:3000/");
    }
});