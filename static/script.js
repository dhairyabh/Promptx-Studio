document.addEventListener("DOMContentLoaded", () => {
  // ========== AUTHENTICATION CHECK ==========
  const userEmail = localStorage.getItem("promptx_user_email");
  if (!userEmail) {
    window.location.href = "/";
    return;
  }

  // ========== DOM ELEMENTS ==========
  const processBtn = document.getElementById("processBtn");
  const fileInput = document.getElementById("video");
  const promptInput = document.getElementById("prompt");
  const voiceBtn = document.getElementById("voiceBtn");
  const resultVideo = document.getElementById("resultVideo");
  
  // Initialize manual editor when file is selected
  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (file && window.initManualEditor) {
        const url = URL.createObjectURL(file);
        window.initManualEditor(url);
      }
    });
  }

  const root = document.documentElement;
  const themeBtn = document.getElementById("themeToggle");
  const themeIcon = document.getElementById("themeIcon");
  const logoutBtn = document.getElementById("logoutBtn");

  if (logoutBtn) {
    logoutBtn.addEventListener("click", (e) => {
      e.preventDefault();
      localStorage.removeItem("promptx_user_email");
      localStorage.removeItem("promptX_usage_count");
      window.location.href = "/";
    });
  }

  // ========== THEME TOGGLE ==========
  if (themeBtn && themeIcon) {
    function applyTheme(theme) {
      root.setAttribute("data-theme", theme);
      localStorage.setItem("theme", theme);
      themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
      themeBtn.title = theme === "dark" ? "Switch to Light" : "Switch to Dark";
    }

    const saved = localStorage.getItem("theme") || "light";
    applyTheme(saved);

    themeBtn.addEventListener("click", () => {
      const current = root.getAttribute("data-theme") || "light";
      applyTheme(current === "light" ? "dark" : "light");
    });
  }

  // ========== VOICE RECOGNITION ==========
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition && voiceBtn) {
    const recognition = new SpeechRecognition();

    // Enhanced accuracy settings
    recognition.continuous = false;  // Automatically stop when user stops speaking
    recognition.lang = 'en-US';
    recognition.interimResults = true;  // Show real-time transcription
    recognition.maxAlternatives = 3;  // Get multiple alternatives for better accuracy

    let finalTranscript = '';
    let isRecording = false;

    voiceBtn.addEventListener("click", () => {
      if (isRecording) {
        recognition.stop();
        isRecording = false;
      } else {
        finalTranscript = '';
        recognition.start();
        isRecording = true;
      }
    });

    recognition.onstart = () => {
      voiceBtn.classList.add("recording");
      voiceBtn.innerText = "🔴";
      promptInput.placeholder = "Listening... Speak now";
    };

    recognition.onend = () => {
      voiceBtn.classList.remove("recording");
      voiceBtn.innerText = "🎤";
      promptInput.placeholder = 'Type "/" to see available audio/video operations, or use voice';
      isRecording = false;
    };

    recognition.onresult = (event) => {
      let interimTranscript = '';

      // Process all results for better accuracy
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;

        if (event.results[i].isFinal) {
          finalTranscript += transcript + ' ';
        } else {
          interimTranscript += transcript;
        }
      }

      // Update input with final + interim results
      promptInput.value = (finalTranscript + interimTranscript).trim();
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      voiceBtn.classList.remove("recording");
      voiceBtn.innerText = "🎤";
      isRecording = false;

      if (event.error === 'no-speech') {
        promptInput.placeholder = "No speech detected. Try again.";
      } else if (event.error === 'audio-capture') {
        promptInput.placeholder = "Microphone not found. Check permissions.";
      } else {
        promptInput.placeholder = "Error: " + event.error;
      }
    };
  } else if (voiceBtn) {
    voiceBtn.style.display = "none";
  }

  // ========== SLASH COMMAND SUGGESTIONS ==========
  const suggestionBox = document.getElementById("suggestionBox");
  const suggestionList = document.getElementById("suggestionList");
  const videoOperations = [
    "Remove silence",
    "Add captions",
    "Make it for Reels",
    "Make it for YouTube Shorts",
    "Auto-zoom on speaker",
    "Color grading",
    "Extract audio",
    "Remove background noise",
    "Add background music",
    "Generate summary",
    "Add B-roll",
    "Resize to 9:16",
    "Resize to 16:9",
  ];
  let slashIndex = -1;
  let selectedSuggestionIndex = -1;

  if (promptInput && suggestionBox && suggestionList) {
    // Show suggestions on input
    promptInput.addEventListener("input", (e) => {
      const val = promptInput.value;
      const cursorPosition = promptInput.selectionStart;

      // Extract text up to the cursor
      const textUpToCursor = val.substring(0, cursorPosition);
      const lastSlashIndex = textUpToCursor.lastIndexOf("/");

      if (lastSlashIndex !== -1) {
        // Check if there is a space after the slash before the cursor
        const textAfterSlash = textUpToCursor.substring(lastSlashIndex + 1);
        if (textAfterSlash.includes(" ")) {
          closeSuggestions();
          return;
        }

        slashIndex = lastSlashIndex;
        const query = textAfterSlash.toLowerCase();

        // Filter operations based on query
        const filteredOps = videoOperations.filter(op => op.toLowerCase().includes(query));

        if (filteredOps.length > 0) {
          renderSuggestions(filteredOps);
        } else {
          closeSuggestions();
        }
      } else {
        closeSuggestions();
      }
    });

    // Keyboard navigation
    promptInput.addEventListener("keydown", (e) => {
      if (!suggestionBox.classList.contains("hidden")) {
        const items = suggestionList.querySelectorAll("li");

        if (e.key === "ArrowDown") {
          e.preventDefault();
          selectedSuggestionIndex = (selectedSuggestionIndex + 1) % items.length;
          updateSelection(items);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          selectedSuggestionIndex = (selectedSuggestionIndex - 1 + items.length) % items.length;
          updateSelection(items);
        } else if (e.key === "Enter" || e.key === "Tab") {
          if (selectedSuggestionIndex >= 0 && selectedSuggestionIndex < items.length) {
            e.preventDefault();
            items[selectedSuggestionIndex].click();
          }
        } else if (e.key === "Escape") {
          closeSuggestions();
        }
      }
    });

    function renderSuggestions(options) {
      suggestionList.innerHTML = "";
      selectedSuggestionIndex = -1;

      options.forEach((op, index) => {
        const li = document.createElement("li");
        li.textContent = op;
        li.addEventListener("click", () => {
          const val = promptInput.value;
          const beforeSlash = val.substring(0, slashIndex);
          // Split the original string by taking the part after the space or end
          const afterWordMatch = val.substring(slashIndex).match(/\\s(.*)/);
          const afterSlashWord = afterWordMatch ? " " + afterWordMatch[1] : "";

          const newValue = beforeSlash + op + (afterSlashWord ? afterSlashWord : ", ");

          promptInput.value = newValue;
          closeSuggestions();
          promptInput.focus();
        });
        suggestionList.appendChild(li);
      });

      suggestionBox.classList.remove("hidden");
    }

    function updateSelection(items) {
      items.forEach((item, index) => {
        if (index === selectedSuggestionIndex) {
          item.classList.add("selected");
          // Scroll item into view if not visible
          item.scrollIntoView({ block: "nearest" });
        } else {
          item.classList.remove("selected");
        }
      });
    }

    function closeSuggestions() {
      suggestionBox.classList.add("hidden");
      suggestionList.innerHTML = "";
      slashIndex = -1;
      selectedSuggestionIndex = -1;
    }

    // Close on click outside
    document.addEventListener("click", (e) => {
      if (e.target !== promptInput && !suggestionBox.contains(e.target)) {
        closeSuggestions();
      }
    });
  }

  // ========== VIDEO PROCESSING ==========
  if (processBtn) {
    processBtn.addEventListener("click", async () => {
      const fileInput = document.getElementById("video");
      const audioInput = document.getElementById("memeAudio");
      const promptInput = document.getElementById("prompt");
      const prompt = promptInput ? promptInput.value.trim() : "";

      // Secret Admin Override checked FIRST before blocking logic
      if (prompt === "dhairya_admin_unlimited") {
        localStorage.setItem("promptx_admin", "true");
        promptInput.value = "";
        updateQuotaUI();
        resultVideo.innerHTML = `<p style="color: #22c55e;">✅ Admin Mode Enabled! You now have unlimited prompts.</p>`;
        return;
      } else if (prompt === "dhairya_user_mode") {
        localStorage.removeItem("promptx_admin");
        promptInput.value = "";
        updateQuotaUI();
        resultVideo.innerHTML = `<p style="color: #38bdf8;">🔄 Admin Mode Disabled. Returned to standard user bounds.</p>`;
        return;
      }

      if (!checkQuota()) return; // Block if quota exceeded

      const file = fileInput ? fileInput.files[0] : null;
      const audioFile = audioInput ? audioInput.files[0] : null;

      if (!file && !prompt) {
        resultVideo.innerHTML = `<p style="color: #ef4444;">❌ Please upload a video or enter a generation prompt.</p>`;
        return;
      }

      // Check if prompt is empty here before beginning any processing
      if (!prompt) {
        resultVideo.innerHTML = `<p style="color: #ef4444;">❌ Please enter a prompt.</p>`;
        return;
      }

      // Decrement usage count right when the process button is clicked and prompt is valid
      if (localStorage.getItem("promptx_admin") !== "true") {
        incrementUsageCount();
      }

      // START PROGRESS BAR
      showProcessingProgress(true);
      startStochasticProgress();
      resultVideo.innerHTML = ""; // Clear old results

      // If no file but there's a prompt, assume generation
      if (!file && prompt) {
        processBtn.disabled = true;
        processBtn.innerText = "Generating...";

        const formData = new FormData();
        formData.append("prompt", prompt);
        formData.append("user_email", userEmail);
        const isAdmin = localStorage.getItem("promptx_admin") === "true";
        formData.append("is_admin", isAdmin);

        try {
          showProcessingProgress(true);
          startStochasticProgress();

          const response = await fetch("/process-video/", {
            method: "POST", body: formData,
          });
          const data = await response.json();

          if (data.error) {
            showProcessingProgress(false);
            resultVideo.innerHTML = `<p style="color: #ef4444;">❌ ${data.error}</p>`;
          } else {
            finishProgress();
            sessionStorage.setItem('last_video_url', data.video_url);
            resultVideo.innerHTML = `
              <p style="color: #22c55e;">✅ Video generated successfully!</p>
              <video controls autoplay>
                <source src="${data.video_url}" type="video/mp4">
              </video>
              <div style="margin-top: 15px; display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;">
                <a href="/editor?video=${encodeURIComponent(data.video_url)}" class="tool-btn-accent" style="text-decoration: none; padding: 10px 20px; font-size: 14px; border-radius: 8px; display: inline-flex; align-items: center; gap: 8px;">
                  <span>✨ Open in Pro Editor</span>
                </a>
                ${createShareButtons(data.video_url)}
              </div>
            `;
          }
        } catch (error) {
          showProcessingProgress(false);
          resultVideo.innerHTML = `<p style="color: #ef4444;">❌ Error: ${error.message}</p>`;
        } finally {
          processBtn.disabled = false;
          processBtn.innerText = "Process Video";
        }
        return;
      }

      // Otherwise, editing mode
      processBtn.disabled = true;
      processBtn.innerText = "Processing...";

      const formData = new FormData();
      formData.append("video", file);
      if (audioFile) formData.append("insert_file", audioFile);
      formData.append("prompt", prompt);
      formData.append("user_email", userEmail);
      const isAdmin = localStorage.getItem("promptx_admin") === "true";
      formData.append("is_admin", isAdmin);

      try {
        showProcessingProgress(true);
        startStochasticProgress();

        const response = await fetch("/process-video/", {
          method: "POST", body: formData,
        });
        const data = await response.json();

        if (data.error) {
          showProcessingProgress(false);
          resultVideo.innerHTML = `<p style="color: #ef4444;">❌ ${data.error}</p>`;
        } else if (data.summary) {
          finishProgress();
          resultVideo.innerHTML = `
            <div class="summary-box">
              <h3>📝 Summary</h3>
              <div class="summary-content">${data.summary}</div>
            </div>
          `;
        } else if (data.video_url && data.video_url.endsWith(".mp3")) {
          finishProgress();
          resultVideo.innerHTML = `
            <p style="color: #22c55e;">✅ Audio extracted successfully!</p>
            <audio controls autoplay>
              <source src="${data.video_url}" type="audio/mpeg">
            </audio>
          `;
        } else {
          finishProgress();
          sessionStorage.setItem('last_video_url', data.video_url);
          resultVideo.innerHTML = `
            <p style="color: #22c55e;">✅ Video processed successfully!</p>
            <video controls autoplay>
              <source src="${data.video_url}" type="video/mp4">
            </video>
            <div style="margin-top: 15px; display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;">
              <a href="/editor?video=${encodeURIComponent(data.video_url)}" class="tool-btn-accent" style="text-decoration: none; padding: 10px 20px; font-size: 14px; border-radius: 8px; display: inline-flex; align-items: center; gap: 8px;">
                <span>✨ Open in Pro Editor</span>
              </a>
              ${createShareButtons(data.video_url)}
            </div>
          `;
        }
      } catch (error) {
        showProcessingProgress(false);
        resultVideo.innerHTML = `<p style="color: #ef4444;">❌ Error: ${error.message}</p>`;
      } finally {
        processBtn.disabled = false;
        processBtn.innerText = "Process Video";
      }
    });
  }

  // ========== FEEDBACK SYSTEM ==========
  const submitFeedbackBtn = document.getElementById("submitFeedback");
  if (submitFeedbackBtn) {
    submitFeedbackBtn.addEventListener("click", async () => {
      const nameInput = document.getElementById("userName");
      const emailInput = document.getElementById("userEmail");
      const messageInput = document.getElementById("userFeedback");
      const feedbackMessage = document.getElementById("feedbackMessage");

      const name = nameInput.value.trim();
      const email = emailInput.value.trim();
      const message = messageInput.value.trim();

      // Basic validation
      if (!name || !email || !message) {
        feedbackMessage.innerHTML = `<p style="color: #ef4444;">❌ Please fill in all fields.</p>`;
        return;
      }

      submitFeedbackBtn.disabled = true;
      submitFeedbackBtn.innerText = "Submitting...";
      feedbackMessage.innerHTML = ""; // Clear previous messages

      try {
        const response = await fetch("/api/feedback", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ name, email, message }),
        });

        const data = await response.json();

        if (data.error) {
          feedbackMessage.innerHTML = `<p style="color: #ef4444;">❌ ${data.error}</p>`;
        } else {
          // Success
          feedbackMessage.innerHTML = `<p style="color: #22c55e;">✅ ${data.message}</p>`;
          // Clear inputs
          nameInput.value = "";
          emailInput.value = "";
          messageInput.value = "";
        }
      } catch (error) {
        feedbackMessage.innerHTML = `<p style="color: #ef4444;">❌ Error submitting feedback. Please try again later.</p>`;
        console.error("Feedback error:", error);
      } finally {
        submitFeedbackBtn.disabled = false;
        submitFeedbackBtn.innerText = "Submit Feedback";
      }
    });
  }

  // ========== QUOTA MANAGEMENT ==========
  const quotaMessageDiv = document.getElementById("quotaMessage");
  const MAX_FREE_PROMPTS = 5;

  function getUsageCount() {
    return parseInt(localStorage.getItem("promptX_usage_count") || "0", 10);
  }

  function incrementUsageCount() {
    const current = getUsageCount();
    localStorage.setItem("promptX_usage_count", current + 1);
    updateQuotaUI();
  }

  function updateQuotaUI() {
    if (!quotaMessageDiv) return;

    // Check if admin mode is on
    if (localStorage.getItem("promptx_admin") === "true") {
      quotaMessageDiv.innerHTML = `<span style="color: #22c55e; font-weight: 800;">Admin Mode (Unlimited Prompts)</span>`;
      return;
    }

    // Check if user has an active Pro subscription (Weekly, Monthly, Annually)
    if (localStorage.getItem("promptx_is_subscribed") === "true") {
      quotaMessageDiv.innerHTML = `<span style="color: #7c3aed; font-weight: 800;">PROMPTX Pro Active (Unlimited)</span>`;
      return;
    }

    const current = getUsageCount();
    const remaining = Math.max(0, MAX_FREE_PROMPTS - current);

    if (remaining === 0) {
      quotaMessageDiv.innerHTML = `<span style="color: #ef4444; font-weight: 800;">Quota Exceeded</span> • <a href="#" id="upgradeLink" style="color: var(--accent); text-decoration: underline; font-weight: 600;">Upgrade</a>`;

      const upgradeLink = document.getElementById("upgradeLink");
      if (upgradeLink) {
        upgradeLink.addEventListener("click", (e) => {
          e.preventDefault();
          document.getElementById("subscriptionModal").style.display = "flex";
        });
      }
    } else {
      // If current usage is negative OR they have the paid user flag, drop the word "Free"
      if (current < 0 || localStorage.getItem("promptx_paid_user") === "true") {
        quotaMessageDiv.innerHTML = `<span id="quotaCount" style="color: var(--text); font-weight: 800;">${remaining}</span> Prompts Remaining`;
      } else {
        quotaMessageDiv.innerHTML = `<span id="quotaCount" style="color: var(--text); font-weight: 800;">${remaining}</span> Free Prompts Remaining`;
      }
    }
  }

  // ========== SUBSCRIPTION & RAZORPAY LOGIC ==========
  const subModal = document.getElementById("subscriptionModal");
  const closeSubModal = document.getElementById("closeSubModal");
  const buyBtns = document.querySelectorAll(".buy-btn");

  if (closeSubModal) {
    closeSubModal.addEventListener("click", () => subModal.style.display = "none");
  }

  // Close modal on outside click
  window.addEventListener("click", (e) => {
    if (e.target === subModal) subModal.style.display = "none";
  });

  // Handle Buy Clicks
  buyBtns.forEach(btn => {
    btn.addEventListener("click", async (e) => {
      const planId = e.target.getAttribute("data-plan");
      const userEmail = localStorage.getItem("promptx_user_email");

      if (!userEmail) {
        alert("Please log in to purchase a subscription.");
        window.location.href = "/";
        return;
      }

      e.target.disabled = true;
      e.target.innerText = "Processing...";

      try {
        // 1. Create Order on Backend
        const orderRes = await fetch("/api/create-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan_id: planId, email: userEmail })
        });

        const orderData = await orderRes.json();
        if (orderData.detail) throw new Error(orderData.detail);

        // 1.5 Fetch Razorpay Config
        const configRes = await fetch("/api/config");
        const configData = await configRes.json();

        if (!configData.razorpay_key_id) {
          throw new Error("Razorpay key not configured on server.");
        }

        // 2. Initialize Razorpay
        const options = {
          key: configData.razorpay_key_id,
          amount: orderData.amount,
          currency: orderData.currency,
          name: "PROMPTX STUDIO",
          description: `Subscription: ${planId.toUpperCase()}`,
          order_id: orderData.order_id,

          handler: async function (response) {
            // 3. Verify Payment on Backend
            try {
              const verifyRes = await fetch("/api/verify-payment", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  razorpay_payment_id: response.razorpay_payment_id,
                  razorpay_order_id: response.razorpay_order_id,
                  razorpay_signature: response.razorpay_signature,
                  email: userEmail,
                  plan_id: planId
                })
              });

              const verifyData = await verifyRes.json();
              if (verifyData.success) {
                alert("Payment Successful! Your account has been upgraded.");
                subModal.style.display = "none";

                // Immediately update local UI so they don't have to refresh
                if (planId === "per_video") {
                  // The backend adds 1 to trials_left, but our frontend currently tracks 
                  // "promptX_usage_count" (how many times they've used it out of 5).
                  // To "add 1 video", we should decrement the usage_count by 1, 
                  // so they get 1 more use before hitting the limit again.
                  let currentUsage = parseInt(localStorage.getItem("promptX_usage_count") || "0");
                  let newUsage = Math.max(0, currentUsage - 1);
                  localStorage.setItem("promptX_usage_count", newUsage.toString());
                  localStorage.setItem("promptx_paid_user", "true");

                  // Also update promptx_trials_left if you use it elsewhere
                  let currentTrials = parseInt(localStorage.getItem("promptx_trials_left") || "0");
                  localStorage.setItem("promptx_trials_left", currentTrials + 1);
                } else {
                  localStorage.setItem("promptx_is_subscribed", "true");
                }

                location.reload(); // Quick refresh to clear old UI state
              } else {
                alert("Payment verification failed.");
              }
            } catch (err) {
              console.error(err);
              alert("An error occurred during verification.");
            }
          },
          prefill: {
            email: userEmail
          },
          theme: {
            color: "#7c3aed"
          }
        };

        const rzp1 = new Razorpay(options);
        rzp1.on('payment.failed', function (response) {
          alert(`Payment Failed: ${response.error.description}`);
        });
        rzp1.open();

      } catch (err) {
        console.error(err);
        alert(err.message || "Failed to initialize payment gateway.");
      } finally {
        e.target.disabled = false;
        e.target.innerText = planId === "per_video" ? "Buy Now" : "Subscribe";
      }
    });
  });

  function checkQuota() {
    if (localStorage.getItem("promptx_admin") === "true") return true;
    if (localStorage.getItem("promptx_is_subscribed") === "true") return true;

    if (getUsageCount() >= MAX_FREE_PROMPTS) {
      if (resultVideo) {
        resultVideo.innerHTML = `
          <div style="background: var(--soft); border: 1px solid var(--border); padding: 16px; border-radius: var(--radius); text-align: center;">
            <p style="font-size: 16px; font-weight: 800; color: #ef4444; margin-bottom: 8px;">🚀 Limit Reached</p>
            <p style="color: var(--text); font-size: 14px; margin-bottom: 12px;">You've used all of your available quota!</p>
            <button id="inlineUpgradeBtn" style="padding: 8px 16px; background: var(--accent); color: white; border: none; cursor: pointer; border-radius: 8px; font-weight: 700; font-size: 14px;">Upgrade to PROMPTX Pro</button>
          </div>
        `;

        // Bind the inline upgrade button to open the modal
        const inlineUpgradeBtn = document.getElementById("inlineUpgradeBtn");
        if (inlineUpgradeBtn && subModal) {
          inlineUpgradeBtn.addEventListener("click", () => subModal.style.display = "flex");
        }
      }
      return false; // Blocks operation
    }
    return true; // Allows operation
  }

  // Initialize Quota UI on load
  updateQuotaUI();

  // ========== CHATBOT WIDGET ==========
  const chatToggle = document.getElementById('chatToggle');
  const chatClose = document.getElementById('chatClose');
  const chatWindow = document.getElementById('chatWindow');
  const chatInput = document.getElementById('chatInput');
  const chatSend = document.getElementById('chatSend');
  const chatMessages = document.getElementById('chatMessages');

  if (chatToggle && chatWindow) {
    // Toggle window
    chatToggle.addEventListener('click', () => {
      chatWindow.classList.toggle('hidden');
      if (!chatWindow.classList.contains('hidden')) {
        chatInput.focus(); // Auto-focus input when opened
      }
    });

    chatClose.addEventListener('click', () => {
      chatWindow.classList.add('hidden');
    });

    // Helper: append message bubble
    function appendMessage(text, sender) {
      const msgDiv = document.createElement('div');
      msgDiv.classList.add('message', sender);

      const bubble = document.createElement('div');
      bubble.classList.add('bubble');

      // Basic formatting for bot lines (newlines to <br>)
      if (sender === 'bot') {
        bubble.innerHTML = text.replace(/\n/g, '<br>');
      } else {
        bubble.textContent = text;
      }

      msgDiv.appendChild(bubble);
      chatMessages.appendChild(msgDiv);
      chatMessages.scrollTop = chatMessages.scrollHeight; // Auto-scroll
      return msgDiv;
    }

    // Send Message
    async function sendMessage() {
      const text = chatInput.value.trim();
      if (!text) return;

      // 1. Show user message
      appendMessage(text, 'user');
      chatInput.value = '';

      // 2. Add 'typing...' indicator
      const typingMsg = appendMessage('Typing...', 'bot');
      chatSend.disabled = true;
      chatInput.disabled = true;

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });

        const data = await response.json();

        // Remove typing indicator
        chatMessages.removeChild(typingMsg);

        if (data.reply) {
          appendMessage(data.reply, 'bot');
        } else {
          appendMessage('Sorry, I encountered an error answering that.', 'bot');
        }
      } catch (err) {
        chatMessages.removeChild(typingMsg);
        appendMessage('Error: Connection failed.', 'bot');
      } finally {
        chatSend.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
      }
    }

    chatSend.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMessage();
    });
  }

  // ========== MOBILE NAVIGATION TOGGLE ==========
  const hamburgerBtn = document.getElementById("hamburgerBtn");
  const navLinksList = document.getElementById("navLinks");
  const navOverlay = document.getElementById("navOverlay");
  const navCloseLinks = document.querySelectorAll(".nav-close-link");

  if (hamburgerBtn && navLinksList && navOverlay) {
    function toggleMobileMenu() {
      const isOpen = navLinksList.classList.contains("active");
      hamburgerBtn.classList.toggle("active", !isOpen);
      navLinksList.classList.toggle("active", !isOpen);
      navOverlay.classList.toggle("active", !isOpen);
      
      // Prevent scrolling when menu is open
      document.body.style.overflow = !isOpen ? "hidden" : "";
    }

    hamburgerBtn.addEventListener("click", toggleMobileMenu);
    navOverlay.addEventListener("click", toggleMobileMenu);

    // Close menu when a link is clicked
    navCloseLinks.forEach(link => {
      link.addEventListener("click", () => {
        if (navLinksList.classList.contains("active")) {
          toggleMobileMenu();
        }
      });
    });
  }

  // ========== PROGRESS BAR ANIMATION LOGIC ==========
  let progressInterval = null;

  function showProcessingProgress(show) {
    const section = document.getElementById("processingSection");
    const resultVideo = document.getElementById("resultVideo");
    if (!section) return;

    if (show) {
      section.style.display = "flex";
      resultVideo.style.display = "none";
      updateProgress(0, "Analyzing Instruction...", "Initializing AI engine and preparing assets...");
    } else {
      section.style.display = "none";
      resultVideo.style.display = "block";
    }
  }

  function updateProgress(percent, header, message) {
    const fill = document.getElementById("progressFill");
    const percentText = document.getElementById("progressPercent");
    const headerText = document.getElementById("statusHeader");
    const msgText = document.getElementById("statusMessage");

    if (fill) fill.style.width = `${percent}%`;
    if (percentText) percentText.innerText = `${Math.floor(percent)}%`;
    if (headerText && header) headerText.innerText = header;
    if (msgText && message) msgText.innerText = message;
  }

  function startStochasticProgress() {
    let currentProgress = 0;
    clearInterval(progressInterval);

    progressInterval = setInterval(() => {
      // Stochastic logic: 
      // 0-20% is fast (upload/parsing)
      // 20-80% is medium (AI processing)
      // 80-99% is slow (Rendering)
      
      let increment = 0;
      if (currentProgress < 20) {
        increment = Math.random() * 2 + 0.5;
        updateProgress(currentProgress, "Analyzing Instruction...", "Uploading assets to secure AI cluster...");
      } else if (currentProgress < 50) {
        increment = Math.random() * 0.5 + 0.1;
        updateProgress(currentProgress, "AI Processing...", "interpreting visual prompts and preparing model weights...");
      } else if (currentProgress < 85) {
        increment = Math.random() * 0.3 + 0.05;
        updateProgress(currentProgress, "Video Rendering...", "Applying frame-by-frame edits and post-processing...");
      } else if (currentProgress < 98) {
        increment = Math.random() * 0.1 + 0.01;
        updateProgress(currentProgress, "Finalizing...", "Wrapping up video container and generating download links...");
      } else {
        increment = 0; // Hold at 98-99% until backend returns
      }

      currentProgress += increment;
      if (currentProgress > 99) currentProgress = 99;
      updateProgress(currentProgress);
    }, 400); // Update every 400ms for smoothness
  }

  function finishProgress() {
    clearInterval(progressInterval);
    updateProgress(100, "Success!", "Video ready. Displaying now...");
    
    // Short delay for visual satisfaction before revealing video
    setTimeout(() => {
      showProcessingProgress(false);
    }, 800);
  }

  function finishProgress() {
    clearInterval(progressInterval);
    updateProgress(100, "Success!", "Video ready. Displaying now...");
    
    // Short delay for visual satisfaction before revealing video
    setTimeout(() => {
      showProcessingProgress(false);
    }, 800);
  }

  // Update processBtn logic to use progress bar
  if (processBtn) {
    // We override the original click listener or wrap it. 
    // Since I can't easily remove anonymous listeners, 
    // I'll replace the block in script.js entirely.
  }
});

