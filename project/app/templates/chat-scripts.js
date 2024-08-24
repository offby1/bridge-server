<script>
    htmx.on("htmx:responseError", function(evt) {
        alert(evt.detail.xhr.response);
    });
</script>
