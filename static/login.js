document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("loginForm");
    const signupForm = document.getElementById("signupForm");
    const toggleBtn = document.getElementById("toggleBtn");
    const formTitle = document.getElementById("formTitle");
    const loginError = document.getElementById("loginError");
    const signupError = document.getElementById("signupError");

    let isLogin = true;

    // Check if user is already logged in
    const userEmail = localStorage.getItem("promptx_user_email");
    if (userEmail) {
        window.location.href = "/app";
    }

    toggleBtn.addEventListener("click", () => {
        isLogin = !isLogin;
        if (isLogin) {
            loginForm.style.display = "block";
            signupForm.style.display = "none";
            formTitle.innerText = "Sign In";
            toggleBtn.innerText = "Need an account? Sign Up";
        } else {
            loginForm.style.display = "none";
            signupForm.style.display = "block";
            formTitle.innerText = "Sign Up";
            toggleBtn.innerText = "Already have an account? Sign In";
        }
        loginError.innerText = "";
        signupError.innerText = "";
    });

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("loginEmail").value;
        const password = document.getElementById("loginPassword").value;
        const btn = loginForm.querySelector('button');

        btn.disabled = true;
        btn.innerText = "Signing In...";
        loginError.innerText = "";

        try {
            const formData = new FormData();
            formData.append("email", email);
            formData.append("password", password);

            const res = await fetch("/api/signin", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                loginError.innerText = data.detail || "Error signing in";
            } else {
                localStorage.setItem("promptx_user_email", data.email);
                localStorage.setItem("promptX_usage_count", 5 - data.trials_left); // Translate trials left to usage count or handle it from DB directly.
                window.location.href = "/app";
            }
        } catch (err) {
            loginError.innerText = "Network Error";
        } finally {
            btn.disabled = false;
            btn.innerText = "Sign In";
        }
    });

    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("signupEmail").value;
        const password = document.getElementById("signupPassword").value;
        const btn = signupForm.querySelector('button');

        btn.disabled = true;
        btn.innerText = "Signing Up...";
        signupError.innerText = "";

        try {
            const formData = new FormData();
            formData.append("email", email);
            formData.append("password", password);

            const res = await fetch("/api/signup", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                signupError.innerText = data.detail || "Error signing up";
            } else {
                localStorage.setItem("promptx_user_email", data.email);
                localStorage.setItem("promptX_usage_count", 0); // 0 used means 5 remaining
                window.location.href = "/app";
            }
        } catch (err) {
            signupError.innerText = "Network Error";
        } finally {
            btn.disabled = false;
            btn.innerText = "Sign Up";
        }
    });

});
