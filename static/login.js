console.log("PROMPTX LOGIN JS LOADED v3.0");
document.addEventListener("DOMContentLoaded", () => {
    const loginForm      = document.getElementById("loginForm");
    const signupForm     = document.getElementById("signupForm");
    const toggleBtn      = document.getElementById("toggleBtn");
    const toggleText     = document.getElementById("toggleText");
    const formTitle      = document.getElementById("formTitle");
    const formSubtitle   = document.getElementById("formSubtitle");
    const loginError     = document.getElementById("loginError");
    const signupError    = document.getElementById("signupError");
    const authIconWrap   = document.querySelector(".auth-icon-wrap");

    let isLogin = true;

    // ── Redirect if already logged in ──
    const userEmail = localStorage.getItem("promptx_user_email");
    if (userEmail) {
        window.location.href = "/app";
        return;
    }

    // ── Animated Prompt Typing Effect ──
    const promptEl  = document.getElementById("promptTyping");
    const prompts   = [
        "Add cinematic fade transition",
        "Remove background noise",
        "Speed up by 2x from 0:10",
        "Add smooth zoom on speaker",
        "Generate auto captions",
        "Color grade to golden hour",
        "Split clip at 0:45",
        "Sync cuts to beat drops",
    ];
    let pIdx = 0, cIdx = 0, deleting = false;

    function typeLoop() {
        if (!promptEl) return;
        const current = prompts[pIdx];

        if (!deleting) {
            promptEl.textContent = current.slice(0, cIdx + 1);
            cIdx++;
            if (cIdx === current.length) {
                deleting = true;
                setTimeout(typeLoop, 2200);
                return;
            }
            setTimeout(typeLoop, 52);
        } else {
            promptEl.textContent = current.slice(0, cIdx - 1);
            cIdx--;
            if (cIdx === 0) {
                deleting = false;
                pIdx = (pIdx + 1) % prompts.length;
                setTimeout(typeLoop, 400);
                return;
            }
            setTimeout(typeLoop, 28);
        }
    }

    setTimeout(typeLoop, 1000);

    // ── Password Eye Toggle ──
    function setupEyeToggle(toggleId, inputId) {
        const btn   = document.getElementById(toggleId);
        const input = document.getElementById(inputId);
        if (!btn || !input) return;

        btn.addEventListener("click", () => {
            const isHidden = input.type === "password";
            input.type = isHidden ? "text" : "password";
            btn.querySelector("svg").style.opacity = isHidden ? "1" : "0.5";
        });
    }

    setupEyeToggle("togglePassLogin",  "loginPassword");
    setupEyeToggle("togglePassSignup", "signupPassword");

    // ── Smooth Form Transition ──
    function switchMode(toLogin) {
        isLogin = toLogin;
        loginError.innerText  = "";
        signupError.innerText = "";

        const showForm = toLogin ? loginForm  : signupForm;
        const hideForm = toLogin ? signupForm : loginForm;

        hideForm.style.opacity = "0";
        hideForm.style.transform = "translateX(20px)";
        setTimeout(() => {
            hideForm.style.display = "none";
            showForm.style.display = "flex";
            showForm.style.opacity = "0";
            showForm.style.transform = "translateX(-20px)";
            requestAnimationFrame(() => {
                showForm.style.transition = "opacity 0.3s ease, transform 0.3s ease";
                showForm.style.opacity = "1";
                showForm.style.transform = "translateX(0)";
            });
        }, 150);

        // Update copy
        if (toLogin) {
            formTitle.innerText    = "Welcome back";
            formSubtitle.innerText = "Sign in to your account to continue creating";
            toggleText.innerText   = "Don't have an account?";
            toggleBtn.innerText    = "Sign Up";
        } else {
            formTitle.innerText    = "Create your account";
            formSubtitle.innerText = "Get started with 5 free video generations";
            toggleText.innerText   = "Already have an account?";
            toggleBtn.innerText    = "Sign In";
        }
    }

    // Init form styles
    loginForm.style.transition  = "opacity 0.3s ease, transform 0.3s ease";
    signupForm.style.transition = "opacity 0.3s ease, transform 0.3s ease";

    toggleBtn.addEventListener("click", () => switchMode(!isLogin));

    // ── Sign In ──
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email    = document.getElementById("loginEmail").value;
        const password = document.getElementById("loginPassword").value;
        const btn      = document.getElementById("loginBtn");

        btn.disabled = true;
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
                // Success flash
                btn.style.background = "linear-gradient(135deg, #059669, #10b981)";
                btn.querySelector("span").innerText = "✓ Redirecting…";
                setTimeout(() => { window.location.href = "/app"; }, 600);
            }
        } catch {
            loginError.innerText = "Network error — please try again.";
        } finally {
            if (btn.querySelector("span").innerText !== "✓ Redirecting…") {
                btn.disabled = false;
                btn.querySelector("span").innerText = "Sign In";
            }
        }
    });

    // ── Sign Up ──
    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email    = document.getElementById("signupEmail").value;
        const password = document.getElementById("signupPassword").value;
        const btn      = document.getElementById("signupBtn");

        btn.disabled = true;
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
                btn.style.background = "linear-gradient(135deg, #059669, #10b981)";
                btn.querySelector("span").innerText = "✓ Account created!";
                setTimeout(() => { window.location.href = "/app"; }, 600);
            }
        } catch {
            signupError.innerText = "Network error — please try again.";
        } finally {
            if (btn.querySelector("span").innerText !== "✓ Account created!") {
                btn.disabled = false;
                btn.querySelector("span").innerText = "Create Account";
            }
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
                                theme:          "filled_black",
                                size:           "large",
                                width:          340,
                                text:           "continue_with",
                                shape:          "rectangular",
                                logo_alignment: "left"
                            }
                        );
                    } else {
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

    // ── Floating particle micro-animation on card hover ──
    const card = document.getElementById("authCard");
    if (card) {
        card.addEventListener("mousemove", (e) => {
            const rect = card.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width - 0.5) * 8;
            const y = ((e.clientY - rect.top)  / rect.height - 0.5) * 8;
            card.style.transform = `perspective(800px) rotateY(${x}deg) rotateX(${-y}deg) scale(1.005)`;
        });

        card.addEventListener("mouseleave", () => {
            card.style.transition = "transform 0.5s ease";
            card.style.transform  = "perspective(800px) rotateY(0deg) rotateX(0deg) scale(1)";
        });

        card.addEventListener("mouseenter", () => {
            card.style.transition = "transform 0.1s ease";
        });
    }
});
