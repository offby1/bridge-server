/**
 * Bridge Game Real-time UI Controller
 * Handles SSE events and DOM updates for the interactive game interface
 */

/**
 * Initialize player-specific event stream (bidding box, hand updates)
 * @param {string} playerEventUrl - SSE endpoint for player-specific events
 * @param {number} playerId - Player ID for redirects
 */
export function initPlayerEventStream(playerEventUrl, playerId) {
    const playerEventSource = new ReconnectingEventSource(playerEventUrl);
    console.log(`Listening for player events on ${playerEventUrl}`);

    let autoScrollTimer;

    playerEventSource.addEventListener('message', function (e) {
        const data = JSON.parse(e.data);
        console.log("Player event listener saw " + Object.keys(data));

        // Handle all fields that might be present in the event
        if ("bidding_box_html" in data) {
            updateBiddingBox(data.bidding_box_html, playerId);
        }

        if ("current_hand_html" in data) {
            autoScrollTimer = updateCurrentHand(data, autoScrollTimer);
        }

        if ("show_hint_button" in data) {
            const btn = document.getElementById("hint-button");
            if (btn) {
                btn.style.visibility = data.show_hint_button ? "visible" : "hidden";
            }
        }
    });

    playerEventSource.addEventListener('stream-reset', function (e) {
        const data = JSON.parse(e.data);
        console.log("playerEventSource got stream-reset: " + Object.keys(data));
    });

    return playerEventSource;
}

/**
 * Initialize table-wide event stream (auction, tricks, game state)
 * @param {string} tableEventUrl - SSE endpoint for table-level events
 */
export function initTableEventStream(tableEventUrl) {
    const handEventSource = new ReconnectingEventSource(tableEventUrl);
    console.log(`Listening for hand events on ${tableEventUrl}`);

    handEventSource.addEventListener('stream-reset', function (e) {
        const data = JSON.parse(e.data);
        console.log("handEventSource got stream-reset: " + Object.keys(data));
    });

    handEventSource.addEventListener('message', function (e) {
        const data = JSON.parse(e.data);
        console.log("Hand event listener saw " + Object.keys(data));

        // Handle all fields that might be present in the event
        // (multiple fields can be sent in a single SSE message)
        if ("trick_counts_string" in data) {
            updateTrickCounts(data.trick_counts_string);
        }

        if ("trick_html" in data) {
            updateTrickDisplay(data.trick_html);
        }

        if ("auction_history_html" in data) {
            updateAuctionHistory(data.auction_history_html);
        }

        if ("contract_text" in data || "final_score" in data || "play_completion_deadline" in data) {
            // Phase transition or game over - reload to show new state
            window.location.reload();
        }
    });

    return handEventSource;
}

/**
 * Update bidding box when it's the player's turn
 * @param {string} html - Rendered bidding box HTML
 * @param {number} playerId - Player ID for redirect on missing container
 */
function updateBiddingBox(html, playerId) {
    const container = document.getElementById("toast-and-bidding-box");

    if (container === null) {
        // Hand ended; redirect to player home
        // TODO: redirect to current hand instead
        window.location = `/player/${playerId}/`;
        return;
    }

    container.innerHTML = html;
    // Re-initialize HTMX event handlers on new buttons
    htmx.process(container);
}

/**
 * Update player's current hand (cards available to play)
 * @param {Object} data - Event data containing current_hand_html and current_hand_direction
 * @param {number} autoScrollTimer - Timer for auto-scroll behavior
 * @returns {number} New timer ID
 */
function updateCurrentHand(data, autoScrollTimer) {
    const { current_hand_html, current_hand_direction, tempo_seconds } = data;
    const container = document.getElementById(current_hand_direction);

    if (container === null) {
        return autoScrollTimer;
    }

    container.outerHTML = current_hand_html;

    const newContainer = document.getElementById(current_hand_direction);
    if (newContainer === null) {
        throw new Error(`After swapping ${current_hand_direction}, element disappeared`);
    }

    htmx.process(newContainer);
    return setupAutoScroll(tempo_seconds, autoScrollTimer);
}

/**
 * Setup auto-scroll to active carousel item after inactivity
 * @param {number} tempoSeconds - Game tempo (time between actions)
 * @param {number} timer - Existing timer to clear
 * @returns {number} New timer ID
 */
function setupAutoScroll(tempoSeconds, timer) {
    clearTimeout(timer);

    const newTimer = setTimeout(() => {
        const activeBit = document.querySelector(".active");
        if (activeBit !== null) {
            activeBit.scrollIntoView();
        }
    }, tempoSeconds * 2000);

    // Cancel auto-scroll on manual scroll
    document.querySelector("ul.carousel")?.addEventListener("scroll", () => {
        clearTimeout(newTimer);
    });

    return newTimer;
}

/**
 * Update trick count display (e.g., "NS: 3, EW: 2")
 * @param {string} trickCountsText - Formatted trick counts
 */
function updateTrickCounts(trickCountsText) {
    const container = document.getElementById("trick-counts-string");
    if (container) {
        container.textContent = trickCountsText;
    }
}

/**
 * Update current trick display (3x3 grid)
 * @param {string} html - Rendered trick HTML
 */
function updateTrickDisplay(html) {
    const container = document.getElementById("_3x3-container");
    if (container) {
        container.innerHTML = html;
        container.scrollIntoView();
    }
}

/**
 * Update auction history table
 * @param {string} html - Rendered auction HTML
 */
function updateAuctionHistory(html) {
    const container = document.getElementById("auction");
    if (container) {
        container.innerHTML = html;
        container.scrollIntoView();
    }
}

/**
 * Initialize carousel prev/next buttons
 */
export function initCarouselButtons() {
    const carousel = document.querySelector("ul.carousel");
    const prevBtn = document.querySelector(".carousel-prev");
    const nextBtn = document.querySelector(".carousel-next");

    if (!carousel || !prevBtn || !nextBtn) return;

    prevBtn.addEventListener("click", () => {
        carousel.scrollBy({ left: -carousel.clientWidth, behavior: "smooth" });
    });
    nextBtn.addEventListener("click", () => {
        carousel.scrollBy({ left: carousel.clientWidth, behavior: "smooth" });
    });
}

/**
 * Initialize error toast for HTMX response errors
 */
export function initErrorToast() {
    htmx.on("htmx:responseError", function(evt) {
        const errorToast = document.getElementById('errorToast');
        const toastBootstrap = bootstrap.Toast.getOrCreateInstance(errorToast);
        const errorText = document.getElementById('errorText');

        errorText.innerHTML = evt.detail.xhr.responseText;
        toastBootstrap.show();
    });
}
