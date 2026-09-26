# Microservices

This directory houses the various microservices that support the main backend application. This decoupled approach
allows for independent scaling, development, and deployment of different parts of the platform's functionality.

## Service Overview

- **`/convertor`**:
    - **Purpose**: Performs video transcoding and processing.
    - **Description**: This service listens for messages on a RabbitMQ queue. When a new video is uploaded, it consumes
      the message, downloads the video from MinIO, transcodes it into different resolutions (e.g., HLS format) using
      FFmpeg, and uploads the results back to MinIO. It is designed to run on GPU-enabled hardware for accelerated
      performance.
