package service;

import client.ApiException;
import client.ApiResponse;

public class ErrorMapper {
    public ApiException retryExhausted(String path, int attempts) {
        return new ApiException("retry exhausted for " + path + " after " + attempts + " attempts");
    }

    public ApiException remoteFailure(String path, ApiResponse response) {
        return new ApiException("remote failure for " + path + ": " + response.getStatusCode());
    }
}
