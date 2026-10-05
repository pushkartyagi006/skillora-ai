/* Skillora AI shared script. Load in <head> on every page. */
(function () {
  const root = document.documentElement;
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = localStorage.getItem("sk_theme") || (dark ? "dark" : "light");

  const P = {
    home: "M3 11l9-8 9 8M5 10v10h14V10",
    file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
    teacher: "M9 4h6v3H9zM7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1M9 14l2 2 4-4",
    hiring: "M16 20v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M21 20v-2a4 4 0 0 0-3-3.9M16 3.1a3.5 3.5 0 0 1 0 6.8",
    mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
    code: "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16",
    user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
    logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
    sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
    moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    menu: "M4 6h16M4 12h16M4 18h16",
    eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6",
    eyeoff: "M3 3l18 18M10.6 10.6a3 3 0 0 0 4.2 4.2M9.9 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 4-.9",
    shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    palette: "M12 3a9 9 0 1 0 0 18c1.4 0 2-1 2-2 0-1.5-1-1.7-1-3 0-1 .8-2 2-2h3a3 3 0 0 0 3-3c0-4-4-8-9-8zM7.5 11h.01M10 7.5h.01M14.5 7.5h.01",
    trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  };
  const ic = (n) => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${P[n]}"/></svg>`;

  // The five features. Add or rename pages here and the sidebar + home cards update everywhere.
  const FEATURES = [
    { id: "resume", name: "Resume AI", href: "/resume.html", icon: "file", color: "#2563EB", desc: "Build and analyze your resume", tag: "Make your resume job-ready", steps: ["Paste the job", "Upload your PDF", "Get score and fixes"] },
    { id: "teacher", name: "Teacher AI", href: "/teacher.html", icon: "teacher", color: "#7C3AED", desc: "Evaluate project reports with ease", tag: "Review student reports in minutes", steps: ["Set the requirements", "Upload the reports", "See who meets them"] },
    { id: "hiring", name: "Hiring AI", href: "/company.html", icon: "hiring", color: "#16A34A", desc: "Screen bulk resumes, find the best", tag: "Find the best candidates fast", steps: ["Add the job", "Upload up to 50 resumes", "Get a ranked list"] },
    { id: "interview", name: "Interview AI", href: "/interview.html", icon: "mic", color: "#F97316", desc: "Practice and get ready", tag: "Practise like it is the real thing", steps: ["Pick role and rounds", "Answer on a timer", "Get your scorecard"] },
    { id: "project", name: "Project AI", href: "/project.html", icon: "code", color: "#0891B2", desc: "Analyze and improve your projects", tag: "Know how strong your project is", steps: ["Describe it", "Get a proof-backed score", "Practise the questions"] },
  ];

  const S = {
    FEATURES, ic,
    token: () => localStorage.getItem("sk_token"),

    async api(path, body, method) {
      const h = { "Content-Type": "application/json" };
      if (S.token()) h.Authorization = "Bearer " + S.token();
      const r = await fetch(path, { method: method || (body ? "POST" : "GET"), headers: h, body: body ? JSON.stringify(body) : undefined });
      let d = {};
      try { d = await r.json(); } catch (e) {}
      if (!r.ok && !d.error) d.error = "Request failed (" + r.status + ")";
      return d;
    },

    // Call on every page that needs a logged-in user. Sends visitors to the login page otherwise.
    async guard() {
      if (!S.token()) { location.replace("/login.html"); return null; }
      const d = await S.api("/api/auth/me");
      if (!d.user) { localStorage.removeItem("sk_token"); location.replace("/login.html"); return null; }
      S.user = d.user;
      return d.user;
    },

    async logout() {
      try { await S.api("/api/auth/logout", {}); } catch (e) {}
      localStorage.removeItem("sk_token");
      location.replace("/login.html");
    },

    setTheme(t) {
      root.dataset.theme = t;
      localStorage.setItem("sk_theme", t);
      S.paintThemeButtons();
    },
    paintThemeButtons() {
      const isDark = root.dataset.theme === "dark";
      document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
        b.innerHTML = ic(isDark ? "sun" : "moon") + (b.dataset.label !== undefined ? (isDark ? "Light theme" : "Dark theme") : "");
        b.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
      });
    },

    // Builds the sidebar. Needs <aside id="side" class="side"></aside> on the page.
    shell(active) {
      const nav = [{ id: "home", name: "Home", href: "/home.html", icon: "home" }, ...FEATURES];
      document.getElementById("side").innerHTML =
        `<a class="brand" href="/home.html"><img src="/assets/logo.png" alt=""><span class="wordmark">Skillora <b>AI</b></span></a>` +
        `<nav>${nav.map((n) => `<a href="${n.href}" class="${n.id === active ? "on" : ""}">${ic(n.icon)}${n.name}</a>`).join("")}</nav>` +
        `<div class="side-bottom"><a href="/profile.html" class="${active === "profile" ? "on" : ""}">${ic("user")}Profile</a>` +
        `<button class="navbtn" data-theme-toggle data-label></button>` +
        `<button class="navbtn" id="logoutBtn">${ic("logout")}Logout</button></div>`;
      document.getElementById("logoutBtn").onclick = S.logout;
      const m = document.getElementById("menuBtn");
      if (m) m.onclick = () => document.getElementById("side").classList.toggle("open");
      S.bindThemeButtons();
    },



    AVATARS: [["#2563EB", "#7C3AED"], ["#0891B2", "#2563EB"], ["#16A34A", "#0891B2"], ["#F97316", "#DB2777"], ["#7C3AED", "#DB2777"]],
    avatarGradient() {
      const i = Number(localStorage.getItem("sk_avatar") || 0) % S.AVATARS.length;
      return `linear-gradient(135deg, ${S.AVATARS[i][0]}, ${S.AVATARS[i][1]})`;
    },

    // Wraps every password box with a show/hide eye button. Safe to call many times.
    addEyes() {
      document.querySelectorAll("input[type=password]").forEach((inp) => {
        if (inp.dataset.eye) return;
        inp.dataset.eye = "1";
        const wrap = document.createElement("div");
        wrap.className = "pwwrap";
        inp.parentNode.insertBefore(wrap, inp);
        wrap.appendChild(inp);
        const b = document.createElement("button");
        b.type = "button";
        b.className = "eye";
        b.title = "Show password";
        b.setAttribute("aria-label", "Show password");
        b.innerHTML = ic("eye");
        b.onclick = () => {
          const show = inp.type === "password";
          inp.type = show ? "text" : "password";
          b.innerHTML = ic(show ? "eyeoff" : "eye");
          b.title = b.ariaLabel = show ? "Hide password" : "Show password";
          inp.focus();
        };
        wrap.appendChild(b);
      });
    },

    // One call per page: login check, sidebar, top bar (title, theme button, user chip).
    // Pages need <aside id="side" class="side"></aside> and <header id="top" class="top"></header>.
    async init(opts) {
      const u = await S.guard();
      if (!u) return null;
      S.shell(opts.active);
      document.getElementById("top").innerHTML =
        `<button class="iconbtn menu" id="menuBtn" aria-label="Open menu">${ic("menu")}</button>` +
        `<div class="grow"><h1>${opts.title}</h1><p>${opts.sub || ""}</p></div>` +
        `<button class="iconbtn" data-theme-toggle></button>` +
        `<a class="userchip" href="/profile.html" title="Your profile"><i style="background:${S.avatarGradient()}">${u.name.trim()[0].toUpperCase()}</i><div><strong>${u.name.replace(/</g, "&lt;")}</strong><small>${u.role}</small></div></a>`;
      document.getElementById("menuBtn").onclick = () => document.getElementById("side").classList.toggle("open");
      S.bindThemeButtons();
      S.addEyes();
      // coloured banner at the top of each feature page
      const f = FEATURES.find((x) => x.id === opts.active);
      const page = document.querySelector(".page");
      if (f && page && !page.querySelector(".pagehero")) {
        page.style.setProperty("--c", f.color);
        page.insertAdjacentHTML("afterbegin",
          `<section class="pagehero"><div class="ph-icon">${ic(f.icon)}</div><div class="ph-text"><h2>${f.tag}</h2><p>${f.desc}</p></div>` +
          `<ol class="ph-steps">${f.steps.map((s, i) => `<li><b>${i + 1}</b>${s}</li>`).join("")}</ol></section>`);
      }
      return u;
    },

    bindThemeButtons() {
      document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
        b.onclick = () => S.setTheme(root.dataset.theme === "dark" ? "light" : "dark");
      });
      S.paintThemeButtons();
    },
  };
  window.Skillora = S;
  document.addEventListener("DOMContentLoaded", () => { S.bindThemeButtons(); S.addEyes(); });
})();
