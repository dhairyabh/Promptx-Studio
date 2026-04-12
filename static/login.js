console.log("PROMPTX LOGIN JS LOADED v2.0");
document.addEventListener("DOMContentLoaded", () => {
    const loginForm      = document.getElementById("loginForm");
    const signupForm     = document.getElementById("signupForm");
    const toggleBtn      = document.getElementById("toggleBtn");
    const toggleText     = document.getElementById("toggleText");
    const formTitle      = document.getElementById("formTitle");
    const formSubtitle   = document.getElementById("formSubtitle");
    const loginError     = document.getElementById("loginError");
    const signupError    = document.getElementById("signupError");

    let isLogin = true;

    // ── Redirect if already logged in ──
    const userEmail = localStorage.getItem("promptx_user_email");
    if (userEmail) {
        window.location.href = "/app";
        return;
    }

    // ── Toggle between Sign In / Sign Up ──
    toggleBtn.addEventListener("click", () => {
        isLogin = !isLogin;
        loginError.innerText = "";
        signupError.innerText = "";

        if (isLogin) {
            loginForm.style.display = "flex";
            signupForm.style.display = "none";
            formTitle.innerText     = "Welcome back";
            formSubtitle.innerText  = "Sign in to your account to continue";
            toggleText.innerText    = "Don't have an account?";
            toggleBtn.innerText     = "Sign Up";
        } else {
            loginForm.style.display = "none";
            signupForm.style.display = "flex";
            formTitle.innerText     = "Create your account";
            formSubtitle.innerText  = "Get started with 5 free video generations";
            toggleText.innerText    = "Already have an account?";
            toggleBtn.innerText     = "Sign In";
        }
    });

    // ── Sign In ──
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email    = document.getElementById("loginEmail").value;
        const password = document.getElementById("loginPassword").value;
        const btn      = document.getElementById("loginBtn");

        btn.disabled    = true;
        btn.querySelector("span").innerText = "Signing in…";
        loginError.innerText = "";

        try {
            const formData = new FormData();
            formData.append("email", email);
            formData.append("password", password);

            const res  = await fetch("/api/signin", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                loginError.innerText = data.detail || "Incorrect email or password.";
            } else {
                localStorage.setItem("promptx_user_email", data.email);
                localStorage.setItem("promptX_usage_count", 5 - data.trials_left);
                window.location.href = "/app";
            }
        } catch {
            loginError.innerText = "Network error — please try again.";
        } finally {
            btn.disabled = false;
            btn.querySelector("span").innerText = "Sign In";
        }
    });

    // ── Sign Up ──
    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email    = document.getElementById("signupEmail").value;
        const password = document.getElementById("signupPassword").value;
        const btn      = document.getElementById("signupBtn");

        btn.disabled    = true;
        btn.querySelector("span").innerText = "Creating account…";
        signupError.innerText = "";

        try {
            const formData = new FormData();
            formData.append("email", email);
            formData.append("password", password);

            const res  = await fetch("/api/signup", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                signupError.innerText = data.detail || "Failed to create account.";
            } else {
                localStorage.setItem("promptx_user_email", data.email);
                localStorage.setItem("promptX_usage_count", 0);
                window.location.href = "/app";
            }
        } catch {
            signupError.innerText = "Network error — please try again.";
        } finally {
            btn.disabled = false;
            btn.querySelector("span").innerText = "Create Account";
        }
    });

    // ── Google Sign-In ──
    async function handleCredentialResponse(response) {
        try {
            const formData = new FormData();
            formData.append("id_token", response.credential);

            const res  = await fetch("/api/google-signin", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                const target = isLogin ? loginError : signupError;
                target.innerText = data.detail || "Google Sign-In failed.";
            } else {
                localStorage.setItem("promptx_user_email", data.email);
                localStorage.setItem("promptX_usage_count", 5 - data.trials_left);
                window.location.href = "/app";
            }
        } catch {
            const target = isLogin ? loginError : signupError;
            target.innerText = "Network error during Google login.";
        }
    }

    // ── Initialize Google Sign-In (with retry) ──
    const initGoogleSignIn = () => {
        fetch("/api/config")
            .then(r => r.json())
            .then(config => {
                const clientId = config.google_client_id;
                if (clientId && clientId !== "YOUR_GOOGLE_CLIENT_ID_HERE") {
                    if (typeof google !== "undefined") {
                        google.accounts.id.initialize({
                            client_id: clientId,
                            callback:  handleCredentialResponse
                        });
                        google.accounts.id.renderButton(
                            document.getElementById("googleBtnContainer"),
                            {
                                theme:          "outline",
                                size:           "large",
                                width:          348,
                                text:           "continue_with",
                                shape:          "rectangular",
                                logo_alignment: "left"
                            }
                        );
                    } else {
                        // Google script still loading — retry
                        setTimeout(initGoogleSignIn, 800);
                    }
                } else {
                    document.getElementById("googleBtnContainer").style.display = "none";
                    document.querySelector(".separator").style.display = "none";
                }
            })
            .catch(() => {
                document.getElementById("googleBtnContainer").style.display = "none";
            });
    };

    initGoogleSignIn();
});
