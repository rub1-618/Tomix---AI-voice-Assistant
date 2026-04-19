// progress shi
const progressBar = document.createElement("div")
progressBar.id = "scroll-progress"
document.body.appendChild(progressBar)

window.addEventListener("scroll", () => {
  const scrollTop = window.scrollY
  const docHeight = document.documentElement.scrollHeight - window.innerHeight
  progressBar.style.width = docHeight > 0 ? (scrollTop / docHeight * 100) + "%" : "0%"
})

// heisenburger

document.getElementById("burger").addEventListener("click", () => {
  document.querySelector("nav ul").classList.toggle("open")
})

// pechiatnaya mashinka nah
const h1 = document.querySelector(".hero h1")
if (h1) {
  const text = h1.textContent
  h1.textContent = ""

  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      observer.disconnect()
      let i = 0
      const type = setInterval(() => {
        h1.textContent += text[i]
        i++
        if (i >= text.length) clearInterval(type)
      }, 60)
    }
  })

  observer.observe(h1)
}

const download_h2 = document.querySelector(".download h2")
if (download_h2) {
  const text = download_h2.textContent
  download_h2.textContent = ""

  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      observer.disconnect()
      let i = 0
      const type = setInterval(() => {
        download_h2.textContent += text[i]
        i++
        if (i >= text.length) clearInterval(type)
      }, 60)
    }
  })

  observer.observe(download_h2)
}

document.querySelectorAll(".pricing-card li").forEach(li => {
  const text = li.textContent
  li.textContent = ""

  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      observer.disconnect()
      let i = 0
      const type = setInterval(() => {
        li.textContent += text[i]
        i++
        if (i >= text.length) clearInterval(type)
      }, 60)
    }
  })

  observer.observe(li)
})

document.querySelectorAll(".media-card h3").forEach(li => {
  const text = li.textContent
  li.textContent = ""

  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      observer.disconnect()
      let i = 0
      const type = setInterval(() => {
        li.textContent += text[i]
        i++
        if (i >= text.length) clearInterval(type)
      }, 60)
    }
  })

  observer.observe(li)
})

document.querySelectorAll(".media-card p").forEach(li => {
  const text = li.textContent
  li.textContent = ""

  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      observer.disconnect()
      let i = 0
      const type = setInterval(() => {
        li.textContent += text[i]
        i++
        if (i >= text.length) clearInterval(type)
      }, 60)
    }
  })

  observer.observe(li)
})

const plugins_h2 = document.querySelector(".plugins h2")
if (plugins_h2) {
  const text = plugins_h2.textContent
  plugins_h2.textContent = ""

  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      observer.disconnect()
      let i = 0
      const type = setInterval(() => {
        plugins_h2.textContent += text[i]
        i++
        if (i >= text.length) clearInterval(type)
      }, 60)
    }
  })

  observer.observe(plugins_h2)
}

// active nav link
document.querySelectorAll("nav a").forEach(link => {
  if (link.href.endsWith(location.pathname.split("/").pop())) {
    link.classList.add("nav-active")
  }
})

// community page
const grid = document.getElementById("plugins-grid")

if (grid) {
  fetch("/api/plugins")
    .then(res => res.json())
    .then(data => {
      grid.innerHTML = ""
      data.forEach(plugin => {
  grid.innerHTML += `<div class="card">
    <h3>${plugin.name}</h3>
    <p>${plugin.description}</p>
    </div>`
})
    })
}

document.querySelectorAll(".card").forEach(card => {
  card.addEventListener("mousemove", (e) => {
      const rect = card.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const centerX = rect.width / 2
      const centerY = rect.height / 2
      const rotateY = (x - centerX) / centerX * 15  // максимум 15 градусов
      const rotateX = (y - centerY) / centerY * -15
    card.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`
  })
})



// main page — карусель скриншотов

const screens = ["screen1.png", "screen2.png", "screen3.png", "screen4.png"]
let current = 0  // индекс текущего скриншота

// находим все три картинки и кнопки
const imgMain = document.getElementById("carousel-img")
const imgPrevSide = document.getElementById("carousel-prev-img")
const imgNextSide = document.getElementById("carousel-next-img")
const btnNext = document.getElementById("next")
const btnPrev = document.getElementById("prev")

// обновляет все три картинки по текущему индексу
function updateCarousel() {
  // % screens.length — закольцовывает индекс (после последнего — первый)
  const prevIndex = (current - 1 + screens.length) % screens.length
  const nextIndex = (current + 1) % screens.length

  imgMain.src = screens[current]       // центральная — текущий
  imgPrevSide.src = screens[prevIndex] // левая — предыдущий
  imgNextSide.src = screens[nextIndex] // правая — следующий
}

if (imgMain) {
  updateCarousel() // заполнить сразу при загрузке
  
btnNext.addEventListener("click", () => {
  current = (current + 1) % screens.length;

  [imgMain, imgPrevSide, imgNextSide].forEach(img => {
    img.classList.remove("slide-right", "slide-left")
    void img.offsetWidth
    img.classList.add("slide-right")
  })

  updateCarousel()
  setTimeout(() => {
    [imgMain, imgPrevSide, imgNextSide].forEach(img => img.classList.remove("slide-right"))
  }, 500)
})


btnPrev.addEventListener("click", () => {
  current = (current - 1 + screens.length) % screens.length;

  [imgMain, imgPrevSide, imgNextSide].forEach(img => {
    img.classList.remove("slide-left", "slide-right")
    void img.offsetWidth
    img.classList.add("slide-left")
  })

  updateCarousel()
  setTimeout(() => {
    [imgMain, imgPrevSide, imgNextSide].forEach(img => img.classList.remove("slide-left"))
  }, 500)
})
}

// profiles blyat
// profile page
const authSection = document.getElementById("auth-section")

// проверяем localStorage при загрузке
const savedEmail = localStorage.getItem("email")

if (savedEmail && document.getElementById("auth-section")) {
  document.getElementById("auth-section").style.display = "none"
  document.getElementById("profile-section").style.display = "block"
  document.getElementById("prof-email").textContent = savedEmail
  document.getElementById("prof-plan").textContent = localStorage.getItem("plan")
  document.getElementById("prof-key").textContent = localStorage.getItem("key")

  document.getElementById("logout-btn").addEventListener("click", () => {
    localStorage.removeItem("email")
    localStorage.removeItem("plan")
    localStorage.removeItem("key")
    location.reload()
  })
}


if (authSection) {
  const profileSection = document.getElementById("profile-section")
  const loginForm = document.getElementById("login-form")
  const registerForm = document.getElementById("register-form")
  const tabLogin = document.getElementById("tab-login")
  const tabRegister = document.getElementById("tab-register")
  const message = document.getElementById("auth-message")

  // переключение вкладок
  tabLogin.addEventListener("click", () => {
    loginForm.style.display = "flex"
    registerForm.style.display = "none"
  })

  tabRegister.addEventListener("click", () => {
    loginForm.style.display = "none"
    registerForm.style.display = "flex"
  })
  loginForm.addEventListener("submit", (e) => {
    e.preventDefault()
    const email = document.getElementById("login-email").value
    const password = document.getElementById("login-password").value

    fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    })
    .then(res => res.json())
    .then(data => {
      if (data.detail) {
        message.textContent = data.detail
      } else {
        localStorage.setItem("email", data.email)
        localStorage.setItem("plan", data.plan)
        localStorage.setItem("key", data.key)
        location.reload()
      }
    })
  })

  registerForm.addEventListener("submit", (e) => {
    e.preventDefault()
    const email = document.getElementById("reg-email").value
    const password = document.getElementById("reg-password").value


    fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    })
    .then(res => res.json())
    .then(data => {
      if (data.detail) {
        message.textContent = data.detail
      } else {
        localStorage.setItem("email", data.email)
        localStorage.setItem("plan", data.plan)
        localStorage.setItem("key", data.key)
        location.reload()
      }
    })
  })
}


//plugin/submit
if (localStorage.getItem("email") && document.getElementById("submit-plugin-section")) {
  document.getElementById("submit-plugin-section").style.display = "block"
  document.getElementById("login-hint").style.display = "none"  // ← вот это
}

if (localStorage.getItem("email") && document.getElementById("submit-plugin-section")) {
  document.getElementById("submit-plugin-section").style.display = "block"
}

const submitForm = document.getElementById("submit-plugin-form")

if (submitForm) {
  submitForm.addEventListener("submit", (e) => {
    e.preventDefault()
    const name = document.getElementById("plugin-name").value
    const desc = document.getElementById("plugin-desc").value
    const code = document.getElementById("plugin-code").value

    fetch("/api/plugins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: desc, code, author_id: localStorage.getItem("key") })
    })
    .then(res => res.json())
    .then(data => {
      document.getElementById("submit-message").textContent = data.message || "Fill in all fields"
  })
  })
}

// grid

const canvas = document.getElementById("grid-canvas")
const ctx = canvas.getContext("2d")

canvas.width = window.innerWidth
canvas.height = window.innerHeight

window.addEventListener("resize", () => {
  canvas.width = window.innerWidth
  canvas.height = window.innerHeight
  offset = 0
})

const step = 40
let offset = 0

function drawGrid() {
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = "rgba(255,255,255,0.08)"
  ctx.lineWidth = 1
  offset += 0.3

  for (let y = -offset % step; y < canvas.height; y += step) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(canvas.width, y)
    ctx.stroke()
  }

  for (let x = -offset % step; x < canvas.width; x += step) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, canvas.height)
    ctx.stroke()
  }

  requestAnimationFrame(drawGrid)
}
drawGrid()

// coursor

const cursor = document.getElementById("cursor")
const dots = []
const amount = 20

for (let i = 0; i < 20; i++) {
  const span = document.createElement("span")
  cursor.append(span)
  dots.push({ x: 0, y: 0, element: span })
}

const mouse = { x: 0, y: 0 }
window.addEventListener("mousemove", e => {
  mouse.x = e.clientX
  mouse.y = e.clientY
})

function animate() {
  dots.forEach((dot, i) => {
    const target = i === 0 ? mouse : dots[i - 1]
    dot.x += (target.x - dot.x) * 0.5
    dot.y += (target.y - dot.y) * 0.5
    dot.element.style.transform = `translate(${dot.x - 13}px, ${dot.y - 13}px)`
  })
  requestAnimationFrame(animate)
}
animate()

// media-screenshots-fan
const fan = document.querySelector(".fan-container")
const spreads = {
  "card-1": "rotate(-25deg) translateX(-200px)",
  "card-2": "rotate(-10deg) translateX(-70px)",
  "card-3": "rotate(10deg)  translateX(70px)",
  "card-4": "rotate(25deg)  translateX(200px)",
}
const defaults = {
  "card-1": "rotate(-15deg) translateX(-120px)",
  "card-2": "rotate(-5deg) translateX(-20px)",
  "card-3": "rotate(5deg)  translateX(20px)",
  "card-4": "rotate(15deg)  translateX(120px)",
}

if (fan) {
  fan.addEventListener("mouseenter", () => {
    for (const cls in spreads) {
      fan.querySelector("." + cls).style.transform = spreads[cls]
    }
  })

  fan.addEventListener("mouseleave", () => {
    for (const cls in defaults) {
      fan.querySelector("." + cls).style.transform = defaults[cls]
    }
  })
}

// cool animations
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add("visible")
      observer.unobserve(entry.target)
    }
  })
}, { threshold: 0.2 })

document.querySelectorAll(".reveal, .reveal-left, .reveal-right").forEach(el => observer.observe(el))

window.addEventListener("load", () => {
  const preloader = document.getElementById("preloader")
  preloader.style.opacity = "0"
  setTimeout(() => preloader.remove(), 500)
})

