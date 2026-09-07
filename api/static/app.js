let sequences = [];
let users = [];

let currentSequenceId = null;


// ============================================================
// INITIALIZE
// ============================================================

async function initialize() {
    try {
        const [sequencesResponse, usersResponse] = await Promise.all([
            fetch("/sequences"),
            fetch("/users")
        ]);

        if (!sequencesResponse.ok) {
            throw new Error("Could not load sequences");
        }

        if (!usersResponse.ok) {
            throw new Error("Could not load users");
        }

        sequences = await sequencesResponse.json();
        users = await usersResponse.json();

        createTabs();

        if (sequences.length > 0) {
            showSequence(sequences[0].id);
        } else {
            document.getElementById("content").innerHTML =
                "<p>No sequences exist.</p>";
        }

    } catch (error) {
        document.getElementById("content").innerHTML =
            `<p class="error">${escapeHtml(error.message)}</p>`;
    }
}


// ============================================================
// CREATE TABS
// ============================================================

function createTabs() {
    const tabs = document.getElementById("tabs");

    tabs.innerHTML = "";

    for (const sequence of sequences) {
        const button = document.createElement("button");

        button.className = "tab";
        button.textContent = sequence.name;

        button.dataset.sequenceId = sequence.id;

        button.addEventListener("click", () => {
            showSequence(sequence.id);
        });

        tabs.appendChild(button);
    }
}


// ============================================================
// SHOW SEQUENCE
// ============================================================

function showSequence(sequenceId) {
    currentSequenceId = sequenceId;

    // Update active tab
    document.querySelectorAll(".tab").forEach(tab => {
        tab.classList.toggle(
            "active",
            Number(tab.dataset.sequenceId) === sequenceId
        );
    });

    const sequence = sequences.find(
        sequence => sequence.id === sequenceId
    );

    const content = document.getElementById("content");

    content.innerHTML = `
        <div class="panel">

            <h2>${escapeHtml(sequence.name)}</h2>


            <!-- ============================================ -->
            <!-- LAST ENTRY -->
            <!-- ============================================ -->

            <div class="section">

                <div class="section-title">
                    Last Entry
                </div>

                <button onclick="getLastEntry(${sequenceId})">
                    Get Last Entry
                </button>

                <input
                    id="last-output"
                    class="output"
                    type="text"
                    readonly
                    value=""
                >

            </div>


            <!-- ============================================ -->
            <!-- NEXT USER -->
            <!-- ============================================ -->

            <div class="section">

                <div class="section-title">
                    Next Entry
                </div>

                <button onclick="getNextUser(${sequenceId})">
                    Get Next Entry
                </button>

                <input
                    id="next-output"
                    class="output"
                    type="text"
                    readonly
                    value=""
                >

            </div>


            <!-- ============================================ -->
            <!-- POST -->
            <!-- ============================================ -->

            <div class="section">

                <div class="section-title">
                    Post to Current Sequence
                </div>

                <div class="post-area">

                    <select id="user-select">
                        <option value="">
                            Select User
                        </option>

                        ${createUserOptions()}

                    </select>

                    <button onclick="postEntry(${sequenceId})">
                        Post
                    </button>

                </div>

                <div id="post-status" class="status"></div>

            </div>

        </div>
    `;
}


// ============================================================
// USER DROPDOWN
// ============================================================

function createUserOptions() {
    return users.map(user => `
        <option value="${user.id}">
            ${escapeHtml(user.name)}
        </option>
    `).join("");
}


// ============================================================
// GET LAST ENTRY
// ============================================================

async function getLastEntry(sequenceId) {
    const output = document.getElementById("last-output");

    output.value = "Loading...";

    try {
        const response = await fetch(
            `/sequences/${sequenceId}/entries/recent`
        );

        if (!response.ok) {
            const error = await response.json();

            throw new Error(
                error.detail || `HTTP ${response.status}`
            );
        }

        const entry = await response.json();

        output.value =
            `${entry.name} — ${formatTimestamp(entry.timestamp)}`;

    } catch (error) {
        output.value = error.message;
    }
}


// ============================================================
// GET NEXT USER
// ============================================================

async function getNextUser(sequenceId) {
    const output = document.getElementById("next-output");

    output.value = "Loading...";

    try {
        const response = await fetch(
            `/sequences/${sequenceId}/next`
        );

        if (!response.ok) {
            const error = await response.json();

            throw new Error(
                error.detail || `HTTP ${response.status}`
            );
        }

        const result = await response.json();

        output.value =
            `${result.name} (position ${result.position})`;

    } catch (error) {
        output.value = error.message;
    }
}


// ============================================================
// POST ENTRY
// ============================================================

async function postEntry(sequenceId) {
    const select = document.getElementById("user-select");
    const status = document.getElementById("post-status");

    const userId = Number(select.value);

    if (!userId) {
        status.className = "status error";
        status.textContent = "Select a user first.";
        return;
    }

    status.className = "status";
    status.textContent = "Posting...";

    try {
        const response = await fetch(
            `/sequences/${sequenceId}/entries`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    user_id: userId
                })
            }
        );

        const result = await response.json();

        if (!response.ok) {
            /*
             * Your API returns a useful error for a wrong user:
             *
             * {
             *     "message": "Wrong user in sequence",
             *     "expected_user_id": ...
             * }
             */

            if (result.detail?.message) {
                throw new Error(result.detail.message);
            }

            throw new Error(
                result.detail || `HTTP ${response.status}`
            );
        }

        status.className = "status success";

        status.textContent =
            `Posted ${result.name} successfully.`;

        /*
         * Refresh the displayed last/next values
         * after a successful post.
         */
        await getLastEntry(sequenceId);
        await getNextUser(sequenceId);

    } catch (error) {
        status.className = "status error";
        status.textContent = error.message;
    }
}


// ============================================================
// FORMAT TIMESTAMP
// ============================================================

function formatTimestamp(timestamp) {
    if (!timestamp) {
        return "";
    }

    const date = new Date(timestamp);

    if (Number.isNaN(date.getTime())) {
        return timestamp;
    }

    return date.toLocaleString();
}


// ============================================================
// HTML ESCAPING
// ============================================================

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


// ============================================================
// START
// ============================================================

initialize();