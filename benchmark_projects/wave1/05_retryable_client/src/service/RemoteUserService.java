package service;

import client.ApiException;
import client.ApiResponse;
import client.HttpClient;
import client.RetryPolicy;

public class RemoteUserService {
    private final HttpClient client;
    private final RetryPolicy retryPolicy;
    private final ErrorMapper errorMapper;

    public RemoteUserService(HttpClient client, RetryPolicy retryPolicy, ErrorMapper errorMapper) {
        this.client = client;
        this.retryPolicy = retryPolicy;
        this.errorMapper = errorMapper;
    }

    public RemoteUser fetchUser(String path) {
        ApiResponse last = null;
        for (int attempt = 1; attempt <= retryPolicy.getMaxAttempts(); attempt++) {
            last = client.get(path);
            if (last.getStatusCode() == 200) {
                return parse(last.getBody());
            }
            if (!retryPolicy.shouldRetry(last.getStatusCode())) {
                throw errorMapper.remoteFailure(path, last);
            }
        }
        throw errorMapper.retryExhausted(path, retryPolicy.getMaxAttempts());
    }

    private RemoteUser parse(String body) {
        String[] parts = body.split(":", 2);
        return new RemoteUser(Integer.parseInt(parts[0]), parts[1]);
    }
}
